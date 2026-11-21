# Phase 3 search experiments

Engine 0.1.0, Python 3.13.15, arm64. Evaluation: default Phase 4 feature model. Fixed depth, no time limit.

## Totals over all positions

| Depth | Experiment | Nodes | Time (s) | NPS | Nodes vs E3 |
|---|---|---:|---:|---:|---:|
| 3 | E1 Minimax | 185,934 | 10.86 | 17,116 | 7.67x |
| 3 | E2 Negamax | 185,934 | 11.17 | 16,643 | 7.67x |
| 3 | E3 Alpha-Beta | 24,249 | 1.78 | 13,595 | 1.00x |
| 3 | E4 + Move Ordering | 7,587 | 0.52 | 14,559 | 0.31x |
| 3 | E5 + Iterative Deepening | 6,825 | 0.46 | 14,721 | 0.28x |
| 3 | E6 + Quiescence | 29,416 | 1.84 | 15,984 | 1.21x |
| 3 | E7 + Transposition Table | 28,004 | 1.81 | 15,473 | 1.15x |
| 4 | E3 Alpha-Beta | 130,177 | 8.42 | 15,465 | 1.00x |
| 4 | E4 + Move Ordering | 31,656 | 2.13 | 14,845 | 0.24x |
| 4 | E5 + Iterative Deepening | 25,924 | 1.68 | 15,393 | 0.20x |
| 4 | E6 + Quiescence | 78,233 | 4.30 | 18,208 | 0.60x |
| 4 | E7 + Transposition Table | 59,523 | 3.57 | 16,659 | 0.46x |

## Per position

| Depth | Experiment | Position | Best | Score | Nodes | Time (s) |
|---|---|---|---|---:|---:|---:|
| 3 | E1 Minimax | start | b1c3 | 72 | 9,322 | 0.52 |
| 3 | E1 Minimax | kiwipete | e2a6 | 506 | 99,949 | 5.86 |
| 3 | E1 Minimax | endgame | b4c4 | 120 | 3,017 | 0.11 |
| 3 | E1 Minimax | tactical | d2d4 | -81 | 9,737 | 0.90 |
| 3 | E1 Minimax | middlegame | d7c8q | 572 | 63,909 | 3.47 |
| 3 | E2 Negamax | start | b1c3 | 72 | 9,322 | 0.52 |
| 3 | E2 Negamax | kiwipete | e2a6 | 506 | 99,949 | 6.06 |
| 3 | E2 Negamax | endgame | b4c4 | 120 | 3,017 | 0.12 |
| 3 | E2 Negamax | tactical | d2d4 | -81 | 9,737 | 0.91 |
| 3 | E2 Negamax | middlegame | d7c8q | 572 | 63,909 | 3.56 |
| 3 | E3 Alpha-Beta | start | b1c3 | 72 | 1,355 | 0.10 |
| 3 | E3 Alpha-Beta | kiwipete | e2a6 | 506 | 11,280 | 0.92 |
| 3 | E3 Alpha-Beta | endgame | b4c4 | 120 | 568 | 0.03 |
| 3 | E3 Alpha-Beta | tactical | d2d4 | -81 | 939 | 0.08 |
| 3 | E3 Alpha-Beta | middlegame | d7c8q | 572 | 10,107 | 0.67 |
| 3 | E4 + Move Ordering | start | b1c3 | 72 | 835 | 0.05 |
| 3 | E4 + Move Ordering | kiwipete | e2a6 | 506 | 3,515 | 0.27 |
| 3 | E4 + Move Ordering | endgame | b4c4 | 120 | 425 | 0.02 |
| 3 | E4 + Move Ordering | tactical | d2d4 | -81 | 487 | 0.04 |
| 3 | E4 + Move Ordering | middlegame | d7c8q | 572 | 2,325 | 0.14 |
| 3 | E5 + Iterative Deepening | start | b1c3 | 72 | 796 | 0.05 |
| 3 | E5 + Iterative Deepening | kiwipete | e2a6 | 506 | 2,961 | 0.23 |
| 3 | E5 + Iterative Deepening | endgame | b4c4 | 120 | 488 | 0.02 |
| 3 | E5 + Iterative Deepening | tactical | d2d4 | -81 | 369 | 0.03 |
| 3 | E5 + Iterative Deepening | middlegame | d7c8q | 572 | 2,211 | 0.13 |
| 3 | E6 + Quiescence | start | b1c3 | 72 | 1,517 | 0.06 |
| 3 | E6 + Quiescence | kiwipete | e2a6 | 92 | 18,964 | 1.34 |
| 3 | E6 + Quiescence | endgame | b4c4 | 26 | 1,146 | 0.03 |
| 3 | E6 + Quiescence | tactical | c4c5 | -382 | 3,229 | 0.25 |
| 3 | E6 + Quiescence | middlegame | d7c8q | 572 | 4,560 | 0.16 |
| 3 | E7 + Transposition Table | start | b1c3 | 72 | 1,241 | 0.05 |
| 3 | E7 + Transposition Table | kiwipete | e2a6 | 92 | 18,460 | 1.32 |
| 3 | E7 + Transposition Table | endgame | b4c4 | 26 | 788 | 0.03 |
| 3 | E7 + Transposition Table | tactical | c4c5 | -382 | 3,205 | 0.25 |
| 3 | E7 + Transposition Table | middlegame | d7c8q | 572 | 4,310 | 0.16 |
| 4 | E3 Alpha-Beta | start | b1c3 | 0 | 7,205 | 0.43 |
| 4 | E3 Alpha-Beta | kiwipete | e2a6 | -6 | 36,120 | 2.38 |
| 4 | E3 Alpha-Beta | endgame | b4c4 | -29 | 2,304 | 0.09 |
| 4 | E3 Alpha-Beta | tactical | g1h1 | -572 | 9,083 | 0.58 |
| 4 | E3 Alpha-Beta | middlegame | d7c8q | 275 | 75,465 | 4.94 |
| 4 | E4 + Move Ordering | start | b1c3 | 0 | 1,705 | 0.10 |
| 4 | E4 + Move Ordering | kiwipete | e2a6 | -6 | 15,013 | 1.10 |
| 4 | E4 + Move Ordering | endgame | b4c4 | -29 | 1,302 | 0.05 |
| 4 | E4 + Move Ordering | tactical | g1h1 | -572 | 5,785 | 0.41 |
| 4 | E4 + Move Ordering | middlegame | d7c8q | 275 | 7,851 | 0.47 |
| 4 | E5 + Iterative Deepening | start | b1c3 | 0 | 2,816 | 0.18 |
| 4 | E5 + Iterative Deepening | kiwipete | e2a6 | -6 | 9,967 | 0.71 |
| 4 | E5 + Iterative Deepening | endgame | b4c4 | -29 | 1,475 | 0.06 |
| 4 | E5 + Iterative Deepening | tactical | g1h1 | -572 | 5,757 | 0.42 |
| 4 | E5 + Iterative Deepening | middlegame | d7c8q | 275 | 5,909 | 0.32 |
| 4 | E6 + Quiescence | start | b1c3 | 0 | 5,321 | 0.23 |
| 4 | E6 + Quiescence | kiwipete | e2a6 | 92 | 41,689 | 2.61 |
| 4 | E6 + Quiescence | endgame | b4f4 | 36 | 3,642 | 0.12 |
| 4 | E6 + Quiescence | tactical | d2d4 | -423 | 12,504 | 0.64 |
| 4 | E6 + Quiescence | middlegame | d7c8q | 512 | 15,077 | 0.69 |
| 4 | E7 + Transposition Table | start | b1c3 | 0 | 3,793 | 0.19 |
| 4 | E7 + Transposition Table | kiwipete | e2a6 | 92 | 30,607 | 2.10 |
| 4 | E7 + Transposition Table | endgame | b4f4 | 36 | 2,073 | 0.07 |
| 4 | E7 + Transposition Table | tactical | d2d4 | -423 | 11,766 | 0.60 |
| 4 | E7 + Transposition Table | middlegame | d7c8q | 512 | 11,284 | 0.62 |
