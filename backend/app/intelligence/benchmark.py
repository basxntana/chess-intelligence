"""Precision / recall / F1 per tactical detector on a labelled dataset (research/datasets/tactics.json).
Shared by the test suite and research/benchmarks/tactics_benchmark.py."""
from __future__ import annotations

import json
from pathlib import Path

from app.chess_core import Position

from .tactics import move_tactics, position_tactics

DATASET = Path(__file__).resolve().parents[3] / "research" / "datasets" / "tactics.json"


def load(path: Path = DATASET) -> dict:
    return json.loads(path.read_text())


def detect(case: dict, data: dict) -> set[str]:
    pos = Position(case["fen"])
    if case.get("move"):
        found = move_tactics(pos, pos.parse_uci(case["move"]))
        return {f["motif"] for f in found} & set(data["move_vocabulary"])
    found = position_tactics(pos)
    labels = set()
    for f in found:
        if f["motif"] not in data["position_vocabulary"]:
            continue
        labels.add(f"checkmate_threat:{f['by']}" if f["motif"] == "checkmate_threat" else f"{f['motif']}:{f['squares'][0]}")
    return labels


def run(data: dict | None = None) -> dict:
    data = data or load()
    per_case, counts = [], {}
    for case in data["cases"]:
        got, want = detect(case, data), set(case["labels"])
        per_case.append({"id": case["id"], "expected": sorted(want), "detected": sorted(got),
                         "false_positives": sorted(got - want), "false_negatives": sorted(want - got)})
        for label, kind in [(x, "tp") for x in got & want] + [(x, "fp") for x in got - want] + \
                           [(x, "fn") for x in want - got]:
            motif = label.split(":")[0]
            counts.setdefault(motif, {"tp": 0, "fp": 0, "fn": 0})[kind] += 1
    metrics = {}
    for motif, c in sorted(counts.items()):
        p = c["tp"] / (c["tp"] + c["fp"]) if c["tp"] + c["fp"] else None
        r = c["tp"] / (c["tp"] + c["fn"]) if c["tp"] + c["fn"] else None
        f1 = 2 * p * r / (p + r) if p and r else 0.0 if p is not None and r is not None else None
        metrics[motif] = {**c, "precision": p, "recall": r, "f1": f1}
    return {"metrics": metrics, "cases": per_case}
