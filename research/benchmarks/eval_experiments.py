"""Phase 4 calibration (Research Question 3): how do evaluation features change decision quality?

Each variant plays the full tapered evaluation (DEFAULT) from 10 openings x both colors at a fixed search depth.
Deterministic: same engine + same depth -> same games. Also records static-eval speed per variant.

Usage (repo root): backend/.venv/bin/python research/benchmarks/eval_experiments.py [depth] [max_plies]
Writes research/reports/eval_experiments.{json,md}.
"""
import json
import math
import os
import platform
import sys
import timeit
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.chess_core import Position
from app.evaluation import DEFAULT, MATERIAL_ONLY, EvalConfig, evaluate
from app.search import SearchConfig, search

OPENINGS = [
    "e2e4 e7e5 g1f3 b8c6", "d2d4 d7d5 c2c4 e7e6", "e2e4 c7c5 g1f3 d7d6", "e2e4 e7e6 d2d4 d7d5",
    "e2e4 c7c6 d2d4 d7d5", "d2d4 g8f6 c2c4 g7g6", "c2c4 e7e5 b1c3 g8f6", "g1f3 d7d5 g2g3 g8f6",
    "e2e4 d7d5 e4d5 d8d5", "d2d4 f7f5 g2g3 g8f6",
]
VARIANTS = {
    "material only": MATERIAL_ONLY,
    "material + PST": replace(MATERIAL_ONLY, pst=True, tapered=True),
    "full, static weights": replace(DEFAULT, tapered=False),
    "full - mobility": replace(DEFAULT, mobility=False),
    "full - pawn structure": replace(DEFAULT, pawn_structure=False),
    "full - king safety": replace(DEFAULT, king_safety=False),
}


def play(args) -> tuple[str, int, str, float]:
    """Returns (variant, game index, result for the variant: 1/0.5/0, reason)."""
    name, i, depth, max_plies = args
    variant, opening = VARIANTS[name], OPENINGS[i // 2].split()
    variant_white = i % 2 == 0
    pos = Position()
    for uci in opening:
        pos.make(pos.parse_uci(uci))
    while (status := pos.status()) == "ongoing" and len(pos._undo) < max_plies:
        white_to_move = pos.turn == "w"
        cfg = variant if white_to_move == variant_white else DEFAULT
        pos.make(pos.parse_uci(search(pos, SearchConfig(depth=depth, eval=cfg)).best_move))
    if status == "checkmate":
        variant_won = (pos.turn == "b") == variant_white  # side to move is mated
        return name, i, status, 1.0 if variant_won else 0.0
    return name, i, status if status != "ongoing" else "ply_limit", 0.5


def elo(score: float) -> float:
    score = min(max(score, 0.01), 0.99)
    return -400 * math.log10(1 / score - 1)


def main(depth: int, max_plies: int) -> None:
    jobs = [(name, i, depth, max_plies) for name in VARIANTS for i in range(2 * len(OPENINGS))]
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as ex:
        games = list(ex.map(play, jobs))
    probe = Position("r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1")
    rows = []
    for name, cfg in VARIANTS.items():
        g = [x for x in games if x[0] == name]
        n, pts = len(g), sum(x[3] for x in g)
        s = pts / n
        margin = 1.96 * math.sqrt(max(s * (1 - s), 0.01) / n)
        rows.append({
            "variant": name, "games": n, "wins": sum(x[3] == 1 for x in g), "draws": sum(x[3] == 0.5 for x in g),
            "losses": sum(x[3] == 0 for x in g), "score": round(s, 3), "elo_vs_full": round(elo(s)),
            "elo_95ci": [round(elo(s - margin)), round(elo(s + margin))],
            "eval_us": round(timeit.timeit(lambda c=cfg: evaluate(probe, c), number=2000) / 2000 * 1e6, 1),
            "endings": {r: sum(x[2] == r for x in g) for r in sorted({x[2] for x in g})},
        })
    reports = ROOT / "research" / "reports"
    (reports / "eval_experiments.json").write_text(json.dumps({"depth": depth, "max_plies": max_plies,
                                                                "results": rows, "games": games}, indent=2))
    md = ["# Phase 4 evaluation experiments", "",
          (f"Each variant vs full tapered evaluation, {len(OPENINGS)} openings x 2 colors, search depth {depth} "
           f"(+quiescence), draw at {max_plies} plies. Python {platform.python_version()}, {platform.machine()}. "
           "Elo is from the variant's view; with 20 games the confidence interval is wide."), "",
          "| Variant | W-D-L | Score | Elo vs full | 95% CI | Eval µs |", "|---|---|---:|---:|---|---:|"]
    md += [f"| {r['variant']} | {r['wins']}-{r['draws']}-{r['losses']} | {r['score']:.2f} | {r['elo_vs_full']:+} | "
           f"{r['elo_95ci'][0]:+} … {r['elo_95ci'][1]:+} | {r['eval_us']} |" for r in rows]
    full_us = round(timeit.timeit(lambda: evaluate(probe, EvalConfig()), number=2000) / 2000 * 1e6, 1)
    md += ["", f"Full evaluation: {full_us} µs per call on kiwipete.", ""]
    (reports / "eval_experiments.md").write_text("\n".join(md))
    print("\n".join(md))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 2, int(sys.argv[2]) if len(sys.argv) > 2 else 160)
