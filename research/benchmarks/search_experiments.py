"""Phase 3 experiments E1-E7: each adds one search technique on top of the previous one.

Usage (from repo root):  backend/.venv/bin/python research/benchmarks/search_experiments.py [depth ...]
Writes research/reports/search_experiments.{json,md}. Fixed depth, no time limit -> node counts are reproducible.
"""
import json
import platform
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.chess_core import START_FEN, Position
from app.config import settings
from app.search import SearchConfig, search

POSITIONS = {
    "start": START_FEN,
    "kiwipete": "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
    "endgame": "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1",
    "tactical": "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1",
    "middlegame": "rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8",
}

OFF = SearchConfig(move_ordering=False, iterative_deepening=False, quiescence=False, transposition_table=False)
EXPERIMENTS = {
    "E1 Minimax": replace(OFF, algorithm="minimax"),
    "E2 Negamax": replace(OFF, algorithm="negamax"),
    "E3 Alpha-Beta": OFF,
    "E4 + Move Ordering": replace(OFF, move_ordering=True),
    "E5 + Iterative Deepening": replace(OFF, move_ordering=True, iterative_deepening=True),
    "E6 + Quiescence": replace(OFF, move_ordering=True, iterative_deepening=True, quiescence=True),
    "E7 + Transposition Table": SearchConfig(),
}
SLOW = {"E1 Minimax", "E2 Negamax"}  # exhaustive; only run at shallow depth
MAX_SLOW_DEPTH = 3


def run(depths: list[int]) -> list[dict]:
    rows = []
    for depth in depths:
        for name, cfg in EXPERIMENTS.items():
            if name in SLOW and depth > MAX_SLOW_DEPTH:
                continue
            for pos_name, fen in POSITIONS.items():
                r = search(Position(fen), replace(cfg, depth=depth))
                rows.append({"experiment": name, "position": pos_name, "depth": depth, "best_move": r.best_move,
                             "score": r.score, "nodes": r.nodes, "time": r.time, "nps": r.nps})
                print(f"d{depth} {name:26} {pos_name:10} {r.best_move:6} {r.score:>7} {r.nodes:>9} {r.time:>8.2f}s",
                      flush=True)
    return rows


def markdown(rows: list[dict]) -> str:
    out = ["# Phase 3 search experiments", "",
           (f"Engine {settings.engine_version}, Python {platform.python_version()}, {platform.machine()}. "
            "Evaluation: default Phase 4 feature model. Fixed depth, no time limit."), "",
           "## Totals over all positions", "",
           "| Depth | Experiment | Nodes | Time (s) | NPS | Nodes vs E3 |", "|---|---|---:|---:|---:|---:|"]
    for depth in sorted({r["depth"] for r in rows}):
        by_exp: dict[str, list[dict]] = {}
        for r in rows:
            if r["depth"] == depth:
                by_exp.setdefault(r["experiment"], []).append(r)
        base = sum(r["nodes"] for r in by_exp["E3 Alpha-Beta"])
        for name, rs in by_exp.items():
            nodes, t = sum(r["nodes"] for r in rs), sum(r["time"] for r in rs)
            out.append(f"| {depth} | {name} | {nodes:,} | {t:.2f} | {int(nodes / t):,} | {nodes / base:.2f}x |")
    out += ["", "## Per position", "", "| Depth | Experiment | Position | Best | Score | Nodes | Time (s) |",
            "|---|---|---|---|---:|---:|---:|"]
    out += [f"| {r['depth']} | {r['experiment']} | {r['position']} | {r['best_move']} | {r['score']} | "
            f"{r['nodes']:,} | {r['time']:.2f} |" for r in rows]
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    depths = [int(a) for a in sys.argv[1:]] or [3, 4]
    results = run(depths)
    reports = ROOT / "research" / "reports"
    (reports / "search_experiments.json").write_text(json.dumps(results, indent=2))
    (reports / "search_experiments.md").write_text(markdown(results))
    print(f"wrote {reports}/search_experiments.(json|md)")
