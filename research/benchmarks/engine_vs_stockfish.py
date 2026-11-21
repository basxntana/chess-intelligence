"""Phase 8.1/8.2: our engine vs the Stockfish reference on research/datasets/benchmark_positions.json.

For every position our engine searches with a fixed time budget; Stockfish then scores *our* move at the label depth.
Metrics per category: best-move agreement, top-3 agreement, average centipawn loss (ACPL), blunder rate (loss >= 200),
evaluation error vs Stockfish (MAE, correlation, sign agreement), and search statistics for both engines.
Stockfish is only a yardstick here; it never produces the app's recommendations.

Usage (repo root): backend/.venv/bin/python research/benchmarks/engine_vs_stockfish.py [seconds_per_move] [workers]
Writes research/reports/engine_vs_stockfish.{json,md}.
"""
import json
import os
import platform
import shutil
import statistics
import sys
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from pathlib import Path

import chess
import chess.engine

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.chess_core import Position
from app.config import settings
from app.search import SearchConfig, search

CLIP = 1000  # centipawns: mate and huge scores are clipped so a few won positions do not dominate averages


@contextmanager
def stockfish():
    """One Stockfish per task. A long-lived engine keeps a non-daemon thread alive in the pool worker, and the
    executor then waits forever for that worker to exit."""
    sf = chess.engine.SimpleEngine.popen_uci(shutil.which("stockfish"))
    try:
        sf.configure({"Threads": 1, "Hash": 64})
        yield sf
    finally:
        sf.quit()


def clip(x: int) -> int:
    return max(-CLIP, min(CLIP, x))


def evaluate_position(args) -> dict:
    p, seconds, label_depth = args
    pos = Position(p["fen"])
    r = search(pos, SearchConfig(depth=30, time_limit=seconds, candidates=1))
    board = chess.Board(p["fen"])
    ours = chess.Move.from_uci(r.best_move)
    with stockfish() as sf:
        info = sf.analyse(board, chess.engine.Limit(depth=label_depth), root_moves=[ours])
        timed = sf.analyse(board, chess.engine.Limit(time=seconds))  # Stockfish with the same budget, for speed
    our_move_cp = info["score"].pov(board.turn).score(mate_score=100_000)
    return {
        "id": p["id"], "category": p["category"], "sf_best": p["best_move"], "our_move": r.best_move,
        "agree": r.best_move == p["best_move"], "top3": r.best_move in p["top3"],
        "cp_loss": max(0, clip(p["eval_cp"]) - clip(our_move_cp)),
        "our_eval": r.score, "sf_eval": p["eval_cp"], "our_mate": r.mate_in,
        "our_depth": r.depth, "our_nodes": r.nodes, "our_nps": r.nps,
        "sf_depth": timed.get("depth"), "sf_nodes": timed.get("nodes"), "sf_nps": timed.get("nps"),
    }


def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    ours = [clip(r["our_eval"]) for r in rows]
    ref = [clip(r["sf_eval"]) for r in rows]
    corr = statistics.correlation(ours, ref) if n > 2 and len(set(ours)) > 1 else None
    return {
        "n": n,
        "best_move_agreement": sum(r["agree"] for r in rows) / n,
        "top3_agreement": sum(r["top3"] for r in rows) / n,
        "acpl": statistics.mean(r["cp_loss"] for r in rows),
        "median_cp_loss": statistics.median(r["cp_loss"] for r in rows),
        "blunder_rate": sum(r["cp_loss"] >= 200 for r in rows) / n,
        "eval_mae": statistics.mean(abs(a - b) for a, b in zip(ours, ref, strict=True)),
        "eval_correlation": corr,
        "eval_sign_agreement": sum((a > 0) == (b > 0) for a, b in zip(ours, ref, strict=True) if abs(b) >= 50)
        / max(1, sum(abs(b) >= 50 for b in ref)),
        "our_mean_depth": statistics.mean(r["our_depth"] for r in rows),
        "our_mean_nps": statistics.mean(r["our_nps"] for r in rows),
        "sf_mean_depth": statistics.mean(r["sf_depth"] or 0 for r in rows),
        "sf_mean_nps": statistics.mean(r["sf_nps"] or 0 for r in rows),
    }


def main(seconds: float, workers: int) -> None:
    data = json.loads((ROOT / "research" / "datasets" / "benchmark_positions.json").read_text())
    jobs = [(p, seconds, data["label_depth"]) for p in data["positions"]]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        rows = list(ex.map(evaluate_position, jobs))
    cats = sorted({r["category"] for r in rows})
    summary = {c: summarize([r for r in rows if r["category"] == c]) for c in cats}
    summary["all"] = summarize(rows)
    meta = {"engine_version": settings.engine_version, "reference": data["reference"],
            "label_depth": data["label_depth"], "seconds_per_move": seconds, "workers": workers,
            "machine": f"{platform.machine()} {platform.processor()}", "python": platform.python_version(),
            "cpus": os.cpu_count()}
    reports = ROOT / "research" / "reports"
    (reports / "engine_vs_stockfish.json").write_text(json.dumps({"meta": meta, "summary": summary, "rows": rows},
                                                                 indent=1))
    pct = lambda x: f"{x:.0%}"
    md = ["# Phase 8: engine vs Stockfish reference", "",
          (f"Custom engine {settings.engine_version}, {seconds}s per move (iterative deepening, all Phase 3-5 "
           f"search features). Reference: {data['reference']} at depth {data['label_depth']}, 1 thread. "
           f"{workers} positions evaluated in parallel on {meta['cpus']} cores ({meta['machine']}). "
           "Scores are from the side to move; centipawn loss = Stockfish's evaluation of its best move minus its "
           f"evaluation of our move, both clipped to ±{CLIP}."), "",
          ("| Category | n | Best-move agreement | Top-3 | ACPL | Median loss | Blunders (≥200) | Eval MAE | "
          "Eval corr. | Sign agree |"),
          "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for c in [*cats, "all"]:
        s = summary[c]
        corr = "–" if s["eval_correlation"] is None else f"{s['eval_correlation']:.2f}"
        md.append(f"| {c} | {s['n']} | {pct(s['best_move_agreement'])} | {pct(s['top3_agreement'])} | "
                  f"{s['acpl']:.0f} | {s['median_cp_loss']:.0f} | {pct(s['blunder_rate'])} | {s['eval_mae']:.0f} | "
                  f"{corr} | {pct(s['eval_sign_agreement'])} |")
    a = summary["all"]
    md += ["", "## Search performance (same time budget)", "",
           "| Engine | Mean depth reached | Mean nodes/s |", "|---|---:|---:|",
           f"| Custom engine (Python) | {a['our_mean_depth']:.1f} | {a['our_mean_nps']:,.0f} |",
           f"| {data['reference']} | {a['sf_mean_depth']:.1f} | {a['sf_mean_nps']:,.0f} |", "",
           (f"Stockfish searches about {a['sf_mean_nps'] / max(a['our_mean_nps'], 1):,.0f}× more nodes per second "
           "(Research Question 6: Python vs optimized native code)."), ""]
    (reports / "engine_vs_stockfish.md").write_text("\n".join(md))
    print("\n".join(md))


if __name__ == "__main__":
    main(float(sys.argv[1]) if len(sys.argv) > 1 else 1.0, int(sys.argv[2]) if len(sys.argv) > 2 else 4)
