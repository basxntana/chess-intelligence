# Phase 4 evaluation experiments

Each variant vs full tapered evaluation, 10 openings x 2 colors, search depth 3 (+quiescence), draw at 160 plies. Python 3.13.15, arm64. Elo is from the variant's view; with 20 games the confidence interval is wide.

| Variant | W-D-L | Score | Elo vs full | 95% CI | Eval µs |
|---|---|---:|---:|---|---:|
| material only | 0-0-20 | 0.00 | -798 | -798 … -536 | 18.6 |
| material + PST | 7-2-11 | 0.40 | -70 | -257 … +81 | 25.2 |
| full, static weights | 5-2-13 | 0.30 | -147 | -383 … +1 | 81.6 |
| full - mobility | 6-5-9 | 0.42 | -53 | -232 … +101 | 77.5 |
| full - pawn structure | 5-6-9 | 0.40 | -70 | -257 … +81 | 58.2 |
| full - king safety | 7-4-9 | 0.45 | -35 | -208 … +121 | 75.8 |

Full evaluation: 84.1 µs per call on kiwipete.
