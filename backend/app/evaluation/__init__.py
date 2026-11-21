"""Phase 4 position evaluation: weighted feature model with tapered (middlegame/endgame) scoring.

evaluate(pos) -> centipawns from White's perspective (search flips the sign for Black).
explain(pos)  -> the same score broken down per term, plus board evidence for each feature.
All weights are initial parameters (TRD 2.5), not chess truths; EvalConfig toggles terms for experiments.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.chess_core import Position
from app.chess_core.board import PAWN_ATTACKS, RAYS, STEPS, WHITE, sq_name

PIECE_VALUES = {"p": 100, "n": 320, "b": 330, "r": 500, "q": 900, "k": 0}
TERMS = ("material", "pst", "mobility", "center_control", "pawn_structure", "king_safety", "piece_coordination")
SQUARES = [r * 16 + f for r in range(8) for f in range(8)]
PHASE_WEIGHT = {"p": 0, "n": 1, "b": 1, "r": 2, "q": 4, "k": 0}
MAX_PHASE = 24  # 4 minors + 4 rooks*2 + 2 queens*4: full middlegame
CENTER = (51, 52, 67, 68)  # d4 e4 d5 e5
WHITE_PIECES, BLACK_PIECES = frozenset("PNBRQK"), frozenset("pnbrqk")

LOWER = {p: p.lower() for p in "PNBRQKpnbrqk"}


@dataclass(frozen=True)
class Weights:
    """(middlegame, endgame) pairs. Mobility is per reachable square above a typical baseline."""
    mobility: tuple = (("n", 4, 4, 4), ("b", 5, 5, 7), ("r", 2, 4, 7), ("q", 1, 2, 14))  # piece, mg, eg, baseline
    center_attack: tuple = (4, 0)
    doubled_pawn: tuple = (-10, -20)
    isolated_pawn: tuple = (-12, -18)
    connected_pawn: tuple = (6, 8)
    pawn_island: tuple = (-5, -10)  # per island beyond the first
    passed_pawn_mg: tuple = (0, 5, 10, 15, 30, 50, 80, 0)  # by relative rank (index 1 = second rank)
    passed_pawn_eg: tuple = (0, 10, 20, 35, 60, 100, 150, 0)
    pawn_shield: tuple = (12, 6)  # own pawn 1 / 2 ranks in front of the king (mg only)
    king_open_file: tuple = (-25, -12)  # no pawns at all / no own pawn, on or beside king file (mg only)
    king_zone_attack: int = -6  # per enemy attack on the king's square and neighbours (mg only)
    bishop_pair: tuple = (30, 50)
    rook_open_file: tuple = (20, 10)
    rook_semi_open_file: tuple = (10, 5)


@dataclass(frozen=True)
class EvalConfig:
    material: bool = True
    pst: bool = True
    mobility: bool = True
    center_control: bool = True
    pawn_structure: bool = True
    king_safety: bool = True
    piece_coordination: bool = True
    tapered: bool = True  # False = static weights: always the middlegame score
    weights: Weights = field(default_factory=Weights)


DEFAULT = EvalConfig()
MATERIAL_ONLY = EvalConfig(pst=False, mobility=False, center_control=False, pawn_structure=False, king_safety=False,
                           piece_coordination=False, tapered=False)

# Piece-square tables, rank 8 first, from White's view. Based on the "Simplified Evaluation Function"
# (chessprogramming.org) as starting parameters. Only the king differs between middlegame and endgame.
_PST = {
    "p": [0, 0, 0, 0, 0, 0, 0, 0, 50, 50, 50, 50, 50, 50, 50, 50, 10, 10, 20, 30, 30, 20, 10, 10,
          5, 5, 10, 25, 25, 10, 5, 5, 0, 0, 0, 20, 20, 0, 0, 0, 5, -5, -10, 0, 0, -10, -5, 5,
          5, 10, 10, -20, -20, 10, 10, 5, 0, 0, 0, 0, 0, 0, 0, 0],
    "n": [-50, -40, -30, -30, -30, -30, -40, -50, -40, -20, 0, 0, 0, 0, -20, -40, -30, 0, 10, 15, 15, 10, 0, -30,
          -30, 5, 15, 20, 20, 15, 5, -30, -30, 0, 15, 20, 20, 15, 0, -30, -30, 5, 10, 15, 15, 10, 5, -30,
          -40, -20, 0, 5, 5, 0, -20, -40, -50, -40, -30, -30, -30, -30, -40, -50],
    "b": [-20, -10, -10, -10, -10, -10, -10, -20, -10, 0, 0, 0, 0, 0, 0, -10, -10, 0, 5, 10, 10, 5, 0, -10,
          -10, 5, 5, 10, 10, 5, 5, -10, -10, 0, 10, 10, 10, 10, 0, -10, -10, 10, 10, 10, 10, 10, 10, -10,
          -10, 5, 0, 0, 0, 0, 5, -10, -20, -10, -10, -10, -10, -10, -10, -20],
    "r": [0, 0, 0, 0, 0, 0, 0, 0, 5, 10, 10, 10, 10, 10, 10, 5, -5, 0, 0, 0, 0, 0, 0, -5, -5, 0, 0, 0, 0, 0, 0, -5,
          -5, 0, 0, 0, 0, 0, 0, -5, -5, 0, 0, 0, 0, 0, 0, -5, -5, 0, 0, 0, 0, 0, 0, -5, 0, 0, 0, 5, 5, 0, 0, 0],
    "q": [-20, -10, -10, -5, -5, -10, -10, -20, -10, 0, 0, 0, 0, 0, 0, -10, -10, 0, 5, 5, 5, 5, 0, -10,
          -5, 0, 5, 5, 5, 5, 0, -5, 0, 0, 5, 5, 5, 5, 0, -5, -10, 5, 5, 5, 5, 5, 0, -10,
          -10, 0, 5, 0, 0, 0, 0, -10, -20, -10, -10, -5, -5, -10, -10, -20],
    "k": [-30, -40, -40, -50, -50, -40, -40, -30, -30, -40, -40, -50, -50, -40, -40, -30,
          -30, -40, -40, -50, -50, -40, -40, -30, -30, -40, -40, -50, -50, -40, -40, -30,
          -20, -30, -30, -40, -40, -30, -30, -20, -10, -20, -20, -20, -20, -20, -20, -10,
          20, 20, 0, 0, 0, 0, 20, 20, 20, 30, 10, 0, 0, 10, 30, 20],
    "k_eg": [-50, -40, -30, -20, -20, -30, -40, -50, -30, -20, -10, 0, 0, -10, -20, -30,
             -30, -10, 20, 30, 30, 20, -10, -30, -30, -10, 30, 40, 40, 30, -10, -30,
             -30, -10, 30, 40, 40, 30, -10, -30, -30, -10, 20, 30, 30, 20, -10, -30,
             -30, -30, 0, 0, 0, 0, -30, -30, -50, -30, -30, -30, -30, -30, -30, -50],
}


def _square_table(table: list[int], white: bool) -> list[int]:
    out = [0] * 128
    for sq in SQUARES:
        r, f = sq >> 4, sq & 7
        out[sq] = table[(7 - r) * 8 + f] if white else table[r * 8 + f]
    return out


PST_MG = {}
PST_EG = {}
for _k in "pnbrqk":
    for _p, _white in ((_k.upper(), True), (_k, False)):
        PST_MG[_p] = _square_table(_PST[_k], _white)
        PST_EG[_p] = _square_table(_PST["k_eg" if _k == "k" else _k], _white)


def evaluate(pos: Position, cfg: EvalConfig = DEFAULT) -> int:
    """Centipawns, White's perspective."""
    return _evaluate(pos, cfg, None)[0]


def explain(pos: Position, cfg: EvalConfig = DEFAULT) -> dict:
    """Score plus per-term contributions (tapered, White's perspective) and supporting board evidence."""
    evidence: list[dict] = []
    total, phase, acc = _evaluate(pos, cfg, evidence)
    terms = {}
    for t in TERMS:
        mg_w, eg_w, mg_b, eg_b = acc[t]
        mg, eg = mg_w - mg_b, eg_w - eg_b
        terms[t] = {"mg": mg, "eg": eg, "score": round(_taper(mg, eg, phase) if cfg.tapered else mg, 1),
                    "white": _taper(mg_w, eg_w, phase) if cfg.tapered else mg_w,
                    "black": _taper(mg_b, eg_b, phase) if cfg.tapered else mg_b}
        terms[t]["white"], terms[t]["black"] = round(terms[t]["white"], 1), round(terms[t]["black"], 1)
    return {"score": total, "phase": phase, "max_phase": MAX_PHASE, "terms": terms, "features": evidence}


def _taper(mg: float, eg: float, phase: int) -> float:
    return (mg * phase + eg * (MAX_PHASE - phase)) / MAX_PHASE


def _evaluate(pos: Position, cfg: EvalConfig, evidence: list | None):
    b, w = pos.board, cfg.weights
    acc = {t: [0, 0, 0, 0] for t in TERMS}  # mg_white, eg_white, mg_black, eg_black

    def add(term: str, c: int, mg: int, eg: int, feature: str | None = None, squares=(), detail=None):
        a = acc[term]
        a[2 * c] += mg
        a[2 * c + 1] += eg
        if evidence is not None and feature:
            evidence.append({"term": term, "feature": feature, "side": "white" if c == 0 else "black",
                             "squares": [sq_name(s) for s in squares], "mg": mg, "eg": eg,
                             **({"detail": detail} if detail else {})})

    # ---- pass 1: material, PST, piece lists, pawn files, phase ----
    # Hot path (runs at every search leaf): accumulate inline instead of through add().
    pieces: tuple[list, list] = ([], [])
    pawns: tuple[list, list] = ([[] for _ in range(8)], [[] for _ in range(8)])  # ranks of pawns per file
    phase = 0
    mat, pst = acc["material"], acc["pst"]
    use_mat, use_pst = cfg.material, cfg.pst
    for sq in SQUARES:
        p = b[sq]
        if p is None:
            continue
        c = 0 if p in WHITE_PIECES else 1
        k = LOWER[p]
        phase += PHASE_WEIGHT[k]
        if use_mat:
            v = PIECE_VALUES[k]
            mat[2 * c] += v
            mat[2 * c + 1] += v
        if use_pst:
            pst[2 * c] += PST_MG[p][sq]
            pst[2 * c + 1] += PST_EG[p][sq]
        if k == "p":
            pawns[c][sq & 7].append(sq >> 4)
        else:
            pieces[c].append((sq, k))
    phase = min(phase, MAX_PHASE)

    # ---- pass 2: attack maps + mobility ----
    need_attacks = cfg.mobility or cfg.center_control or cfg.king_safety
    att = ([0] * 128, [0] * 128)
    if need_attacks:
        mob = {k: (mg, eg, base) for k, mg, eg, base in w.mobility}
        mob_acc, use_mob = acc["mobility"], cfg.mobility
        for c in (0, 1):
            a = att[c]
            enemy = BLACK_PIECES if c == 0 else WHITE_PIECES
            pawn_att = PAWN_ATTACKS[c]
            for f in range(8):
                for r in pawns[c][f]:
                    for t in pawn_att[r * 16 + f]:
                        a[t] += 1
            for sq, k in pieces[c]:
                count = 0
                if k in STEPS:
                    for t in STEPS[k][sq]:
                        a[t] += 1
                        q = b[t]
                        if q is None or q in enemy:
                            count += 1
                else:
                    for ray in RAYS[k][sq]:
                        for t in ray:
                            a[t] += 1
                            q = b[t]
                            if q is None:
                                count += 1
                            else:
                                if q in enemy:
                                    count += 1
                                break
                if use_mob and k in mob:
                    mg, eg, base = mob[k]
                    mob_acc[2 * c] += (count - base) * mg
                    mob_acc[2 * c + 1] += (count - base) * eg
                    if evidence is not None:
                        evidence.append({"term": "mobility", "feature": "piece_mobility",
                                         "side": "white" if c == 0 else "black", "squares": [sq_name(sq)],
                                         "mg": (count - base) * mg, "eg": (count - base) * eg,
                                         "detail": {"piece": k, "moves": count}})

    # ---- center control ----
    if cfg.center_control:
        for c in (0, 1):
            ac = att[c]
            n = ac[51] + ac[52] + ac[67] + ac[68]  # CENTER, unrolled (hot path)
            if n:
                add("center_control", c, n * w.center_attack[0], n * w.center_attack[1], "center_attacks",
                    [s for s in CENTER if att[c][s]], {"attacks": n})

    # ---- pawn structure (cached by pawn formation; computed fully when evidence is requested) ----
    if cfg.pawn_structure:
        if evidence is not None:
            _pawn_structure(pawns, w, add)
        else:
            cache = _pawn_cache(w)
            key = (tuple(map(tuple, pawns[0])), tuple(map(tuple, pawns[1])))
            terms = cache.get(key)
            if terms is None:
                terms = [0, 0, 0, 0]

                def add_terms(_term, c, mg, eg, *_rest, **_kw):
                    terms[2 * c] += mg
                    terms[2 * c + 1] += eg
                _pawn_structure(pawns, w, add_terms)
                if len(cache) >= PAWN_CACHE_MAX:
                    cache.clear()
                cache[key] = terms
            ps = acc["pawn_structure"]
            for idx in range(4):
                ps[idx] += terms[idx]

    # ---- king safety (middlegame terms; tapering fades them out in the endgame) ----
    if cfg.king_safety:
        for c, color in ((0, WHITE), (1, "b")):
            ksq = pos.kings[color]
            if ksq is None:
                continue
            kf, kr, fwd = ksq & 7, ksq >> 4, (1 if c == 0 else -1)
            own, opp = pawns[c], pawns[1 - c]
            shield, files = [], []
            for f in range(max(0, kf - 1), min(7, kf + 1) + 1):
                if kr + fwd in own[f]:
                    shield.append(((kr + fwd) * 16 + f, w.pawn_shield[0]))
                elif kr + 2 * fwd in own[f]:
                    shield.append(((kr + 2 * fwd) * 16 + f, w.pawn_shield[1]))
                if not own[f]:
                    files.append((f, w.king_open_file[0] if not opp[f] else w.king_open_file[1]))
            if shield:
                add("king_safety", c, sum(v for _, v in shield), 0, "pawn_shield", [s for s, _ in shield])
            if files:
                add("king_safety", c, sum(v for _, v in files), 0, "open_files_near_king",
                    detail={"files": ["abcdefgh"[f] for f, _ in files]})
            zone = [ksq, *STEPS["k"][ksq]]
            opp_att = att[1 - c]
            hits = 0
            for zs in zone:
                hits += opp_att[zs]
            if hits:
                add("king_safety", c, hits * w.king_zone_attack, 0, "king_zone_attacked",
                    [s for s in zone if att[1 - c][s]], {"attacks": hits})

    # ---- piece coordination ----
    if cfg.piece_coordination:
        for c in (0, 1):
            own, opp = pawns[c], pawns[1 - c]
            bishops = [s for s, k in pieces[c] if k == "b"]
            if len(bishops) >= 2:
                add("piece_coordination", c, w.bishop_pair[0], w.bishop_pair[1], "bishop_pair", bishops)
            for s, k in pieces[c]:
                if k == "r" and not own[s & 7]:
                    mg, eg = w.rook_open_file if not opp[s & 7] else w.rook_semi_open_file
                    add("piece_coordination", c, mg, eg,
                        "rook_open_file" if not opp[s & 7] else "rook_semi_open_file", [s])

    mg = sum(a[0] - a[2] for a in acc.values())
    eg = sum(a[1] - a[3] for a in acc.values())
    total = round(_taper(mg, eg, phase)) if cfg.tapered else mg
    return total, phase, acc


def _pawn_structure(pawns: tuple[list, list], w: Weights, add) -> None:
    """Pawn-structure terms; depends only on the pawns, so results are cacheable by formation."""
    for c in (0, 1):
        own, opp = pawns[c], pawns[1 - c]
        islands, prev = 0, False
        for f in range(8):
            has = bool(own[f])
            islands += has and not prev
            prev = has
        if islands > 1:
            n = islands - 1
            add("pawn_structure", c, n * w.pawn_island[0], n * w.pawn_island[1], "pawn_islands",
                detail={"islands": islands})
        for f in range(8):
            ranks = own[f]
            if not ranks:
                continue
            squares = [r * 16 + f for r in ranks]
            if len(ranks) > 1:
                n = len(ranks) - 1
                add("pawn_structure", c, n * w.doubled_pawn[0], n * w.doubled_pawn[1], "doubled_pawns", squares)
            left, right = own[f - 1] if f > 0 else [], own[f + 1] if f < 7 else []
            if not left and not right:
                n = len(ranks)
                add("pawn_structure", c, n * w.isolated_pawn[0], n * w.isolated_pawn[1], "isolated_pawn",
                    squares)
            for r in ranks:
                rel = r if c == 0 else 7 - r
                behind = r - 1 if c == 0 else r + 1  # a pawn here defends r
                if any(x in (r, behind) for x in left + right):
                    add("pawn_structure", c, w.connected_pawn[0], w.connected_pawn[1], "connected_pawn",
                        [r * 16 + f])
                blockers = (x for ff in (f - 1, f, f + 1) if 0 <= ff < 8 for x in opp[ff])
                if not any((x > r) if c == 0 else (x < r) for x in blockers):
                    add("pawn_structure", c, w.passed_pawn_mg[rel], w.passed_pawn_eg[rel], "passed_pawn",
                        [r * 16 + f], {"relative_rank": rel + 1})


PAWN_CACHE_MAX = 200_000  # shortcut: cleared when full instead of LRU; formations repeat heavily within a search
_PAWN_CACHES: dict[int, tuple[Weights, dict]] = {}


def _pawn_cache(w: Weights) -> dict:
    entry = _PAWN_CACHES.get(id(w))
    if entry is None or entry[0] is not w:  # the Weights object is kept in the entry so its id cannot be reused
        entry = _PAWN_CACHES[id(w)] = (w, {})
    return entry[1]
