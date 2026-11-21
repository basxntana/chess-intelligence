# Phase 8: engine vs Stockfish reference

Custom engine 0.1.0, 1.0s per move (iterative deepening, all Phase 3-5 search features). Reference: Stockfish 19 at depth 18, 1 thread. 4 positions evaluated in parallel on 8 cores (arm64 arm). Scores are from the side to move; centipawn loss = Stockfish's evaluation of its best move minus its evaluation of our move, both clipped to ±1000.

| Category | n | Best-move agreement | Top-3 | ACPL | Median loss | Blunders (≥200) | Eval MAE | Eval corr. | Sign agree |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| endgame | 40 | 32% | 82% | 36 | 0 | 5% | 121 | 0.97 | 100% |
| opening | 40 | 22% | 55% | 33 | 24 | 0% | 45 | 0.73 | 82% |
| random | 40 | 80% | 90% | 31 | 2 | 5% | 166 | 0.96 | 97% |
| tactical | 60 | 75% | 92% | 103 | 4 | 17% | 295 | 0.69 | 88% |
| all | 180 | 55% | 81% | 57 | 4 | 8% | 172 | 0.91 | 93% |

## Search performance (same time budget)

| Engine | Mean depth reached | Mean nodes/s |
|---|---:|---:|
| Custom engine (Python) | 4.3 | 15,704 |
| Stockfish 19 | 32.2 | 426,091 |

Stockfish searches about 27× more nodes per second (Research Question 6: Python vs optimized native code).
