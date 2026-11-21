"""Turn an analysis (app.intelligence.analyze) into a flat list of verified facts with ids.
Explanations, rule-based or LLM, may only state what these facts contain and must cite their ids."""
from __future__ import annotations

from app.chess_core import Position
from app.chess_core.notation import line_san, san
from app.intelligence import position_tactics

PIECE = {"p": "pawn", "n": "knight", "b": "bishop", "r": "rook", "q": "queen", "k": "king"}
WARN_MOTIFS = {"hanging_piece", "checkmate_threat", "pin", "skewer"}
EVAL_TERM_MIN = 15  # centipawns: smaller static-eval changes are noise
STRATEGIC_SKIP = {"connected_pawn", "pawn_islands", "semi_open_file", "open_file"}


def piece_name(letter: str | None) -> str:
    return PIECE[letter.lower()] if letter else "piece"


def pawns(cp: int) -> str:
    return f"{cp / 100:+.2f}"


def build_facts(pos: Position, analysis: dict, move: str | None = None) -> list[dict]:
    """Facts about `move` (UCI; default: the engine's best) in the analysed position."""
    cands = analysis["candidates"]
    cand = next((c for c in cands if c["move"] == move), None) if move else cands[0] if cands else None
    if cand is None:
        raise ValueError(f"move {move!r} is not one of the analysed candidates")
    mover = analysis["side_to_move"]
    sign = 1 if mover == "white" else -1
    m = pos.parse_uci(cand["move"])
    move_san = san(pos, m)
    pv_san = line_san(pos, cand["pv"])
    facts = [
        {"id": "move", "type": "move", "uci": cand["move"], "san": move_san, "side": mover,
         "pv_uci": cand["pv"], "pv_san": pv_san, "depth": cand["depth"],
         "best": cand["move"] == cands[0]["move"]},
        {"id": "eval", "type": "evaluation", "score_cp": None if cand["mate_in"] is not None else cand["score"],
         "pawns": None if cand["mate_in"] is not None else pawns(cand["score"]),
         "perspective": mover, "mate_in": cand["mate_in"], "depth": cand["depth"]},
    ]

    # Tactics the move creates.
    for i, t in enumerate(cand["tactics"], 1):
        ev = dict(t["evidence"])
        if "mating_moves" in ev:  # show mates in SAN from the position where they would be played
            ev["mating_moves_san"] = _mating_san(pos, m, t["by"], ev["mating_moves"])
        facts.append({"id": f"t{i}", "type": "tactic", "motif": t["motif"], "by": t["by"], "against": t["against"],
                      "squares": t["squares"], "material_gain": ev.get("material_gain", t["severity"]
                      if t["motif"] in ("hanging_piece", "material_gain") else None),
                      "verified": t["verified"], "evidence": ev})

    # Threats against the mover before the move, and whether the move deals with them.
    pos.make(m)
    after = {(t["motif"], tuple(t["squares"])) for t in position_tactics(pos)}
    pos.unmake()
    for i, t in enumerate((t for t in analysis["position"]["tactics"]
                           if t["against"] == mover and t["motif"] in WARN_MOTIFS), 1):
        moved_away = t["motif"] == "hanging_piece" and t["squares"] and t["squares"][0] == cand["move"][:2]
        resolved = moved_away or (t["motif"], tuple(t["squares"])) not in after
        facts.append({"id": f"w{i}", "type": "threat_before_move", "motif": t["motif"], "by": t["by"],
                      "against": t["against"], "squares": t["squares"], "resolved_by_move": resolved,
                      "evidence": t["evidence"]})

    # Strategic features the move creates or removes.
    i = 0
    for change, items in (("gained", cand["strategic_changes"]["gained"]), ("lost", cand["strategic_changes"]["lost"])):
        for f in items:
            if f["feature"] in STRATEGIC_SKIP:
                continue
            i += 1
            facts.append({"id": f"s{i}", "type": "strategic_change", "change": change, "feature": f["feature"],
                          "category": f["category"], "side": f["side"], "squares": f["squares"],
                          "evidence": f["evidence"]})

    # Static evaluation terms that moved noticeably (mover's perspective).
    i = 0
    for term, delta in sorted(cand["eval_change"].items(), key=lambda kv: -abs(kv[1])):
        if term != "material" and abs(delta) >= EVAL_TERM_MIN:
            i += 1
            facts.append({"id": f"e{i}", "type": "eval_term_change", "term": term, "delta_cp": round(delta * sign),
                          "pawns": pawns(round(delta * sign)), "perspective": mover})

    # Alternatives.
    for i, c in enumerate((c for c in cands if c["move"] != cand["move"]), 1):
        mate_involved = c["mate_in"] is not None or cand["mate_in"] is not None  # mate scores are not centipawns
        diff = None if mate_involved else c["score"] - cand["score"]
        facts.append({"id": f"c{i}", "type": "alternative", "uci": c["move"], "san": san(pos, pos.parse_uci(c["move"])),
                      "score_cp": None if c["mate_in"] is not None else c["score"],
                      "pawns": None if c["mate_in"] is not None else pawns(c["score"]), "mate_in": c["mate_in"],
                      "better": c["score"] > cand["score"],
                      "difference_cp": diff, "difference_pawns": None if diff is None else pawns(diff)})
    return facts


def _mating_san(pos: Position, m, by: str, mates: list[str]) -> list[str]:
    """Mating moves are found in a null-move position after `m`; convert them to SAN there."""
    from app.chess_core.attacks import with_turn  # local: avoids a cycle at import time

    pos.make(m)
    try:
        q = with_turn(pos, "w" if by == "white" else "b")
        return [san(q, q.parse_uci(u)) for u in mates]
    finally:
        pos.unmake()
