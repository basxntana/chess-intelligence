"""Tactical motif detection (TRD 3.2).

Two levels:
  position_tactics(pos)  - facts true on the board now: hanging pieces, pins, skewers, mate threats.
  move_tactics(pos, m)   - what a move creates: check/mate, fork, discovered attack, double attack, new pins/skewers,
                           mate threats, and pieces it leaves hanging.
Material-winning motifs (fork, skewer, discovered/double attack) are geometric patterns that must also be
*verified*: a short material-only search after the move must confirm a gain of >= VERIFY_GAIN, so motifs that the
opponent can refute (e.g. by capturing the forking piece) are not reported.
"""
from __future__ import annotations

from app.chess_core import Move, Position
from app.chess_core.attacks import SLIDER_DIRS, SQUARES, attackers, attacks_from, see, value, with_turn
from app.chess_core.board import BLACK, WHITE, parse_sq, sq_name
from app.evaluation import MATERIAL_ONLY, evaluate
from app.search import MATE, SearchConfig, search

VERIFY_GAIN = 100  # centipawns of material the motif must win to count
VERIFY_DEPTH = 3  # opponent reply, our follow-up, their recapture (+ quiescence)
NAME = {WHITE: "white", BLACK: "black"}


def other(color: str) -> str:
    return BLACK if color == WHITE else WHITE


def _is(color: str, piece: str | None) -> bool:
    return piece is not None and piece.isupper() == (color == WHITE)


def finding(motif: str, by: str, squares, severity: int, evidence: dict, verified: bool | None = None) -> dict:
    return {"category": "tactical", "motif": motif, "by": NAME[by], "against": NAME[other(by)],
            "squares": [sq_name(s) for s in squares], "severity": severity, "verified": verified,
            "evidence": evidence}


# ---------- position-level facts ----------
def threats(pos: Position, color: str) -> dict[int, dict]:
    """Enemy pieces `color` could win right now by a legal capture with positive static exchange."""
    q = with_turn(pos, color)
    out: dict[int, dict] = {}
    for m in q.legal_moves():
        target = q.board[m.to]
        if not target or target in "Kk":
            continue
        gain = see(q.board, m.frm, m.to)
        if gain > 0:
            e = out.setdefault(m.to, {"gain": 0, "by": []})
            e["gain"] = max(e["gain"], gain)
            if m.frm not in e["by"]:
                e["by"].append(m.frm)
    return out


def mating_moves(pos: Position, color: str) -> list[str]:
    """Mate-in-one moves `color` has (or would have if it were their turn)."""
    if pos.turn != color and pos.in_check(color):
        return []  # color is in check now: a "pass" by the opponent is meaningless
    q = with_turn(pos, color)
    if q.in_check(other(color)):
        return []  # null move would leave the opponent's king capturable
    mates = []
    for m in q.legal_moves():
        q.make(m)
        if q.in_check() and not q.legal_moves():
            mates.append(m.uci)
        q.unmake()
    return mates


def line_tactics(pos: Position) -> list[dict]:
    """Pins (front piece worth less than the one behind) and skewers (front piece worth more) by sliders."""
    b, out = pos.board, []
    for s in SQUARES:
        p = b[s]
        if not p or p.lower() not in SLIDER_DIRS:
            continue
        us = WHITE if p.isupper() else BLACK
        for d in SLIDER_DIRS[p.lower()]:
            t, front = s + d, None
            while not t & 0x88:
                if b[t]:
                    if _is(us, b[t]):
                        break
                    if front is None:
                        front = t
                    else:
                        vf, vb = value(b[front]), value(b[t])
                        ev = {"attacker": sq_name(s), "front": sq_name(front), "behind": sq_name(t),
                              "pieces": [p, b[front], b[t]]}
                        if vb > vf:
                            out.append(finding("pin", us, [front], vf, {**ev, "absolute": b[t] in "Kk"}))
                        elif vf > vb:
                            bb = b[:]
                            bb[front] = None
                            defended = bool(attackers(bb, t, not p.isupper()))
                            if not defended or vb > value(p):
                                out.append(finding("skewer", us, [front], vb, {**ev, "behind_defended": defended}))
                        break
                t += d
    return out


def position_tactics(pos: Position) -> list[dict]:
    out = []
    for color in (WHITE, BLACK):
        for sq, t in threats(pos, color).items():
            owner_white = pos.board[sq].isupper()
            out.append(finding("hanging_piece", color, [sq], t["gain"], {
                "piece": pos.board[sq], "attackers": [sq_name(s) for s in t["by"]],
                "defenders": [sq_name(s) for s in attackers(pos.board, sq, owner_white)], "expected_gain": t["gain"]}))
        mates = mating_moves(pos, color)
        if mates:
            out.append(finding("checkmate_threat", color, [parse_sq(u[2:4]) for u in mates], MATE,
                               {"mating_moves": mates, "immediate": pos.turn == color}))
    return out + line_tactics(pos)


# ---------- move-level ----------
def _line_key(f: dict) -> tuple:
    e = f["evidence"]
    return f["motif"], e["attacker"], e["front"], e["behind"]


def material_swing(pos_after: Position, us: str, before: int) -> int:
    """Material change for `us` after best play (material-only search, opponent to move)."""
    r = search(pos_after, SearchConfig(depth=VERIFY_DEPTH, eval=MATERIAL_ONLY, candidates=1))
    if r.terminal == "checkmate" or (r.mate_in is not None and r.mate_in < 0):
        return MATE
    if r.mate_in is not None:
        return -MATE
    return -r.score - before


def move_tactics(pos: Position, m: Move, verify: bool = True) -> list[dict]:
    us, them = pos.turn, other(pos.turn)
    sign = 1 if us == WHITE else -1
    material_before = evaluate(pos, MATERIAL_ONLY) * sign
    threats_before = threats(pos, us)
    ours_hanging_before = threats(pos, them)
    lines_before = {_line_key(f) for f in line_tactics(pos) if f["by"] == NAME[us]}
    frm = m.frm
    pos.make(m)
    try:
        return _after_move(pos, m, us, them, frm, material_before, threats_before, ours_hanging_before,
                           lines_before, verify)
    finally:
        pos.unmake()


def _after_move(pos, m, us, them, frm, material_before, threats_before, ours_hanging_before, lines_before, verify):
    b, out = pos.board, []
    if pos.in_check():
        if not pos.legal_moves():
            return [finding("checkmate", us, [m.to], MATE, {"move": m.uci}, True)]
        checkers = attackers(b, pos.kings[them], us == WHITE)
        out.append(finding("check", us, checkers, 0, {"move": m.uci, "checkers": [sq_name(s) for s in checkers]}))
    in_check = bool(out)
    gain = material_swing(pos, us, material_before) if verify else None
    verified = gain is not None and gain >= VERIFY_GAIN

    # Targets "worth attacking": the king, a more valuable piece, or one that can be won by exchange.
    def worth(attacker_sq: int, target_sq: int) -> bool:
        t = b[target_sq]
        return _is(them, t) and (t in "Kk" or value(t) > value(b[attacker_sq]) or see(b, attacker_sq, target_sq) > 0)

    # Fork: the moved piece hits two or more such targets.
    fork = [t for t in attacks_from(b, m.to) if worth(m.to, t)]
    if len(fork) >= 2 and verified:
        out.append(finding("fork", us, [m.to, *fork], gain, {
            "piece": b[m.to], "from": sq_name(m.to), "targets": [sq_name(t) for t in fork],
            "target_pieces": [b[t] for t in fork], "material_gain": gain}, True))

    # Discovered attack: a slider of ours now sees a target through the square the moved piece left.
    discovered = []
    for s in SQUARES:
        p = b[s]
        if s == m.to or not _is(us, p) or p.lower() not in SLIDER_DIRS:
            continue
        for d in SLIDER_DIRS[p.lower()]:
            t, through = s + d, False
            while not t & 0x88:
                if t == frm:
                    through = True
                elif b[t]:
                    if through and worth(s, t):
                        discovered.append((s, t))
                    break
                t += d
    if discovered and verified:
        out.append(finding("discovered_attack", us, [frm] + [x for st in discovered for x in st], gain, {
            "moved_piece": b[m.to], "uncovered": [{"attacker": sq_name(s), "target": sq_name(t), "piece": b[t]}
                                                  for s, t in discovered],
            "check": any(b[t] in "Kk" for _, t in discovered), "material_gain": gain}, True))

    # Double attack: two or more threats that no single piece makes alone, at least one new.
    targets = {sq: set(t["by"]) for sq, t in threats(pos, us).items()}
    if in_check:
        targets[pos.kings[them]] = set(attackers(b, pos.kings[them], us == WHITE))
    new = [t for t in targets if t not in threats_before]
    if len(targets) >= 2 and new and not set.intersection(*targets.values()) and verified:
        out.append(finding("double_attack", us, list(targets), gain, {
            "targets": [{"square": sq_name(t), "piece": b[t], "attackers": sorted(sq_name(a) for a in by)}
                        for t, by in targets.items()], "material_gain": gain}, True))

    # New pins / skewers made by this move (skewers must win material).
    for f in line_tactics(pos):
        if f["by"] != NAME[us] or _line_key(f) in lines_before:
            continue
        if f["motif"] == "pin" or verified:
            out.append({**f, "verified": True if f["motif"] == "skewer" else None})

    # Mate threat: if the opponent passed, we would mate.
    if not in_check and (mates := mating_moves(pos, us)):
        out.append(finding("checkmate_threat", us, [], MATE, {"mating_moves": mates}))

    # Pieces of ours the opponent can now win that were not en prise before.
    for sq, t in threats(pos, them).items():
        if t["gain"] >= VERIFY_GAIN and t["gain"] > ours_hanging_before.get(sq, {}).get("gain", 0):
            out.append(finding("hanging_piece", them, [sq], t["gain"], {
                "piece": b[sq], "attackers": [sq_name(a) for a in t["by"]], "expected_gain": t["gain"],
                "left_by_move": m.uci}))

    if gain is not None and gain >= VERIFY_GAIN and not any(f["motif"] in MATERIAL_MOTIFS for f in out):
        out.append(finding("material_gain", us, [m.to], gain, {"move": m.uci, "material_gain": gain}, True))
    return out


MATERIAL_MOTIFS = {"fork", "discovered_attack", "double_attack", "skewer"}
