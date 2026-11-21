# Phase 5 tactical detection benchmark

Dataset `research/datasets/tactics.json`: 27 cases (19 move-level, 8 position-level), 0.2s.

> The dataset was written alongside the detectors, so these numbers are a regression check, not an independent accuracy estimate (that needs an external labelled set; see Phase 8). While labelling, the engine verifier rejected three of the author's own 'tactics' that the opponent could refute; they are kept as negative cases.

| Motif | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
| checkmate_threat | 3 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| discovered_attack | 2 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| double_attack | 2 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| fork | 3 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| hanging_piece | 5 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| pin | 5 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| skewer | 2 | 0 | 0 | 1.00 | 1.00 | 1.00 |

## False positives / negatives

None.

## Random positions (not hand-picked)

200 positions from seeded random play, 3 ms each for position-level detection. Findings: checkmate_threat 1, hanging_piece 690, pin 190, skewer 18.
Invariant violations (hanging without a winning capture, wrong pin/skewer geometry, mating move that does not mate): **0**.

Move-level analysis (incl. verification search): 78 ms per move on average.
