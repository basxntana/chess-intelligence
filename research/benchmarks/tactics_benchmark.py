"""Phase 5: precision/recall per tactical detector + invariant checks on random positions.

Usage (repo root): backend/.venv/bin/python research/benchmarks/tactics_benchmark.py
Writes research/reports/tactics_benchmark.{json,md}.
"""
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.chess_core import Position
from app.chess_core.attacks import see, value
from app.chess_core.board import parse_sq
from app.intelligence import position_tactics
from app.intelligence.benchmark import load, run
from app.intelligence.tactics import move_tactics


def random_positions(n: int, seed: int = 11) -> list[Position]:
    rng, out = random.Random(seed), []
    while len(out) < n:
        pos = Position()
        for _ in range(rng.randint(6, 70)):
            moves = pos.legal_moves()
            if not moves:
                break
            pos.make(rng.choice(moves))
        if pos.legal_moves():
            out.append(Position(pos.fen()))
    return out


def invariant_violations(pos: Position) -> list[str]:
    """Independent sanity rules every position-level finding must satisfy."""
    bad, b = [], pos.board
    for f in position_tactics(pos):
        sq = parse_sq(f["squares"][0]) if f["squares"] else None
        if f["motif"] == "hanging_piece":
            gains = [see(b, parse_sq(a), sq) for a in f["evidence"]["attackers"]]
            if not b[sq] or max(gains) <= 0:
                bad.append(f"hanging without winning capture: {f['squares']}")
        elif f["motif"] in ("pin", "skewer"):
            e = f["evidence"]
            front, behind = b[parse_sq(e["front"])], b[parse_sq(e["behind"])]
            ok = value(behind) > value(front) if f["motif"] == "pin" else value(front) > value(behind)
            if not ok or front.isupper() != behind.isupper():
                bad.append(f"{f['motif']} geometry wrong at {e}")
        elif f["motif"] == "checkmate_threat":
            for u in f["evidence"]["mating_moves"]:
                q = Position(pos.fen())
                if q.turn[0] != f["by"][0]:
                    q = Position(" ".join([q.fen().split()[0], f["by"][0]] + q.fen().split()[2:3] + ["-", "0", "1"]))
                q.make(q.parse_uci(u))
                if not q.is_checkmate():
                    bad.append(f"mating move {u} does not mate")
    return bad


def main() -> None:
    data = load()
    t = time.perf_counter()
    result = run(data)
    dataset_time = time.perf_counter() - t

    positions = random_positions(200)
    t = time.perf_counter()
    counts: dict[str, int] = {}
    violations = []
    for pos in positions:
        for f in position_tactics(pos):
            counts[f["motif"]] = counts.get(f["motif"], 0) + 1
        violations += [(pos.fen(), v) for v in invariant_violations(pos)]
    random_time = time.perf_counter() - t
    t = time.perf_counter()
    move_counts: dict[str, int] = {}
    for pos in positions[:40]:
        m = pos.legal_moves()[0]
        for f in move_tactics(pos, m):
            move_counts[f["motif"]] = move_counts.get(f["motif"], 0) + 1
    move_time = (time.perf_counter() - t) / 40

    reports = ROOT / "research" / "reports"
    (reports / "tactics_benchmark.json").write_text(json.dumps(
        {**result, "random_positions": {"n": len(positions), "findings": counts, "violations": violations,
                                        "move_findings_first_move": move_counts}}, indent=2))
    md = ["# Phase 5 tactical detection benchmark", "",
          (f"Dataset `research/datasets/tactics.json`: {len(data['cases'])} cases "
          f"({sum(bool(c.get('move')) for c in data['cases'])} move-level, "
          f"{sum(not c.get('move') for c in data['cases'])} position-level), {dataset_time:.1f}s."), "",
          ("> The dataset was written alongside the detectors, so these numbers are a regression check, not an "
          "independent accuracy estimate (that needs an external labelled set; see Phase 8). While labelling, the "
          "engine verifier rejected three of the author's own 'tactics' that the opponent could refute; they are kept "
          "as negative cases."), "",
          "| Motif | TP | FP | FN | Precision | Recall | F1 |", "|---|---:|---:|---:|---:|---:|---:|"]
    fmt = lambda x: "–" if x is None else f"{x:.2f}"
    md += [f"| {m} | {v['tp']} | {v['fp']} | {v['fn']} | {fmt(v['precision'])} | {fmt(v['recall'])} | "
           f"{fmt(v['f1'])} |" for m, v in result["metrics"].items()]
    errors = [c for c in result["cases"] if c["false_positives"] or c["false_negatives"]]
    md += ["", "## False positives / negatives", ""]
    md += [f"- `{c['id']}`: FP {c['false_positives']}, FN {c['false_negatives']}" for c in errors] or ["None."]
    md += ["", "## Random positions (not hand-picked)", "",
           f"{len(positions)} positions from seeded random play, {random_time / len(positions) * 1000:.0f} ms each "
           "for position-level detection. Findings: "
           + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())) + ".",
           (f"Invariant violations (hanging without a winning capture, wrong pin/skewer geometry, mating move that "
           f"does not mate): **{len(violations)}**."), "",
           f"Move-level analysis (incl. verification search): {move_time * 1000:.0f} ms per move on average.", ""]
    (reports / "tactics_benchmark.md").write_text("\n".join(md))
    print("\n".join(md))


if __name__ == "__main__":
    main()
