"""Phase 5 position intelligence: structured, evidence-backed facts about a position and its candidate moves."""
from __future__ import annotations

from dataclasses import asdict

from app.chess_core import Position
from app.evaluation import TERMS, explain
from app.search import MATE, MATE_BOUND, Candidate, SearchConfig, SearchResult, mate_in, search

from .strategy import feature_changes, strategic_features
from .tactics import move_tactics, position_tactics

SCHEMA_VERSION = 1


def analyze(pos: Position, cfg: SearchConfig | None = None, result: SearchResult | None = None,
            extra_moves: list[str] | None = None) -> dict:
    """Roadmap pipeline: validated position -> features -> candidates -> simulate -> evaluate -> changes -> facts.
    `pos` must already be validated as legal. Scores/terms are from White's perspective.
    `extra_moves` (UCI) are analysed too even if the engine did not rank them, e.g. a move the user played."""
    cfg = cfg or SearchConfig()
    result = result or search(pos, cfg)
    before = explain(pos)
    strategic_before = strategic_features(pos, before)
    ranked = [(c, result.depth) for c in result.candidates]
    extra_depth = max(result.depth, cfg.depth)
    for uci in extra_moves or []:
        if all(c.move != uci for c, _ in ranked):
            ranked.append((score_move(pos, pos.parse_uci(uci), extra_depth, cfg), extra_depth))
    candidates = [candidate_entry(pos, c, depth, before, strategic_before) for c, depth in ranked]
    return {
        "schema_version": SCHEMA_VERSION,
        "fen": pos.fen(),
        "side_to_move": "white" if pos.turn == "w" else "black",
        "search": asdict(result),
        "position": {
            "static_eval": before["score"], "phase": before["phase"], "terms": before["terms"],
            "tactics": position_tactics(pos), "strategic": strategic_before,
        },
        "candidates": candidates,
    }


def candidate_entry(pos: Position, c: Candidate, depth: int, before: dict | None = None,
                    strategic_before: list | None = None) -> dict:
    """Simulate one candidate move: tactics it creates, static-eval change per term, strategic changes."""
    before = before or explain(pos)
    strategic_before = strategic_before if strategic_before is not None else strategic_features(pos, before)
    m = pos.parse_uci(c.move)
    tactics = move_tactics(pos, m)
    pos.make(m)
    after = explain(pos)
    strategic_after = strategic_features(pos, after)
    pos.unmake()
    return {
        "move": c.move, "score": c.score, "mate_in": c.mate_in, "pv": c.pv, "depth": depth,
        "tactics": tactics,
        "eval_change": {t: round(after["terms"][t]["score"] - before["terms"][t]["score"], 1) for t in TERMS},
        "static_eval_after": after["score"],
        "strategic_changes": feature_changes(strategic_before, strategic_after),
    }


def score_move(pos: Position, m, depth: int, cfg: SearchConfig) -> Candidate:
    """Score one specific move: search the reply position one ply shallower (side-to-move perspective)."""
    pos.make(m)
    try:
        child = search(pos, SearchConfig(**{**asdict(cfg), "eval": cfg.eval, "depth": max(depth - 1, 1),
                                            "candidates": 1, "time_limit": None}))
    finally:
        pos.unmake()
    if child.terminal == "checkmate":
        score = MATE - 1
    elif child.terminal == "stalemate":
        score = 0
    else:
        score = -child.score + (1 if child.score > MATE_BOUND else -1 if child.score < -MATE_BOUND else 0)
    return Candidate(m.uci, score, [m.uci, *child.pv], mate_in(score))


__all__ = ["SCHEMA_VERSION", "analyze", "candidate_entry", "move_tactics", "position_tactics", "score_move", "strategic_features"]
