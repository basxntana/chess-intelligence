# Phase 8: playing-strength estimate

Custom engine (over UCI) vs Stockfish with UCI_LimitStrength, 0.5s per move for both, 8 openings × both colors per level, draw adjudicated at 200 plies. Games: `elo_match.pgn`.

| Opponent UCI_Elo | Games | W-D-L | Score | Avg plies |
|---:|---:|---|---:|---:|
| 1320 | 16 | 12-3-1 | 0.84 | 96 |
| 1500 | 16 | 12-2-2 | 0.81 | 86 |
| 1700 | 16 | 5-3-8 | 0.41 | 125 |

**Estimated rating: 1669** (95% interval 1554–1783), maximum likelihood over all 48 games against the opponents' nominal UCI_Elo.

Game endings: checkmate 40, insufficient_material 2, max_plies 3, threefold_repetition 3.

Caveats: UCI_Elo is Stockfish's own calibration at long time controls, not a FIDE rating; the interval reflects game count only, not anchor error. A score of 0 or 1 against every level means the rating lies outside the tested range and the estimate is a bound.
