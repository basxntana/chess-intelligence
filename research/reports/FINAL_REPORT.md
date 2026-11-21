# Chess Intelligence: final project report

Engine version 0.1.0 · Python 3.13 on an Apple M2 (8 cores) · reference engine Stockfish 19 (benchmarking only).
Every number below comes from a script in `research/benchmarks/` and a report next to this file; rerun them to
reproduce. Fixed-depth results are deterministic; time-limited results vary slightly with machine load.

## 1. What was built

| Phase | Deliverable | Verified by |
|---|---|---|
| 1 Foundation | FastAPI backend, Next.js frontend, Docker/CI config | app runs locally; CI workflow (not yet run on GitHub) |
| 2 Chess core | 0x88 board, FEN, legal moves, make/unmake, draw rules, position validator, Zobrist hashing, SAN | perft on 6 reference positions (depth 3-4); SAN identical to python-chess on 18,546 random moves |
| 3 Search | minimax, negamax, alpha-beta, move ordering (TT/MVV-LVA/killer/history), iterative deepening, quiescence with SEE + delta pruning, transposition table, multi-PV, time limits, UCI interface | alpha-beta score = exhaustive minimax at depth 1-3 on 5 positions |
| 4 Evaluation | tapered weighted model: material, piece-square tables, mobility, center, pawn structure, king safety, piece coordination; per-term breakdown with evidence | exact color symmetry on 155 positions; 12 curated "A better than B" pairs |
| 5 Intelligence | tactical detectors (fork, pin, skewer, hanging piece, discovered/double attack, mate threat) with exchange evaluation and engine verification; strategic features; per-move analysis pipeline | 27-case labelled set; 0 rule violations on 200 random positions |
| 6 Explanation | fact list per move → rule-based explanation + optional Claude explanation, grounding validator with rule-based fallback | 100% of rule-based sentences grounded; 12 hallucination types rejected in tests |
| 7 Web app | interactive board, position editor, analysis dashboard, move explorer, explanations, history; async jobs; PostgreSQL + Alembic | driven end-to-end in Chrome (Playwright), no console errors |
| 8 Evaluation & deployment | Stockfish benchmark, Elo estimate, explanation evaluation, production config, logging, metrics | this report; production builds run locally |

423 automated tests pass (`backend/tests`). All recommendations come from the custom engine; Stockfish is used only
in `research/benchmarks/` and tests never depend on it.

## 2. Research questions

**RQ1 – Alpha-beta vs minimax** (`search_experiments.md`). Over 5 positions at depth 3, alpha-beta searched
24,249 nodes against minimax's 185,934 (7.7× fewer) and ran in 1.8 s instead of 10.9 s, with identical root scores
(checked by tests).

**RQ2 – Move ordering.** Ordering cut nodes to 0.31× of plain alpha-beta at depth 3 and 0.24× at depth 4;
iterative deepening with previous-iteration ordering brought depth 4 to 0.20×. Quiescence search *adds* nodes
(0.60× instead of 0.20× at depth 4) in exchange for tactically stable scores; the transposition table recovers part of
that (0.46×).

**RQ3 – Evaluation features** (`eval_experiments.md`, 20 self-play games per variant at depth 3, run before the
Phase 5 change to exchange evaluation). Material-only evaluation lost all 20 games to the full model. Removing any one
term or the middlegame/endgame tapering scored 0.30–0.45 (−35 to −147 Elo), but with 20 games only the
material-only gap is statistically clear; the full model costs 84 µs per evaluation versus 19 µs for material only.

**RQ4 – Rule-based tactical detection** (`tactics_benchmark.md`). On the 27-case labelled set every detector scored
precision and recall 1.00 with no false positives. That set was written alongside the detectors, so it is a
regression check, not an independent accuracy estimate. Two stronger signals: (a) on 200 random positions no finding
broke its definition (hanging pieces always had a winning capture, pin/skewer geometry was always right, every
reported mating move mated); (b) while the set was being written, the engine verifier rejected three of the
author's own "tactics" that the opponent could refute (…Rg7+, …Rc7, …Rd7). They are kept as negative cases.
Not measured: accuracy on an external, independently labelled puzzle set.

**RQ5 – Hybrid explanations** (`explanation_eval.md`, 180 benchmark positions). Rule-based explanations:
1,622 sentences, all grounded in engine facts; the summary always named the recommended move, which was always legal
(python-chess). Checked independently against Stockfish depth 16: 5/5 "forced mate in N" claims held; 77/88 (88%)
"wins about X pawns" claims were matched by Stockfish's own line; the stated evaluation had Stockfish's sign in 94%
of positions (median gap 111 cp). Every unconfirmed claim traces to the engine's depth-4 search, not to the
explanation layer (for example `tactical-048`, where the engine missed a mate Stockfish found). The Claude path is
built and tested against a fake client and the real SDK without credentials (rule-based fallback), but was **not run
against the live API** here; `explanation_live_check.py` measures its grounding rejection rate once a key is set.
Clarity for human readers was not measured (needs human raters).

**RQ6 – Python vs native** (`engine_vs_stockfish.md`). With 1 s per move and one thread each, the Python engine
reached depth 4.3 at about 15,700 nodes/s; Stockfish reached depth 32 at about 426,000 nodes/s (27× the node rate, with
far stronger pruning and an NNUE evaluation on top).

## 3. Engine quality against the reference

`engine_vs_stockfish.md`: 180 positions (opening, random, tactical, endgame), 1 s per move, labels from Stockfish 19 at
depth 18.

| Category | Best-move agreement | Top-3 | Avg centipawn loss | Blunders (≥200 cp) |
|---|---:|---:|---:|---:|
| opening | 22% | 55% | 33 | 0% |
| random | 80% | 90% | 31 | 5% |
| tactical | 75% | 92% | 103 | 17% |
| endgame | 32% | 82% | 36 | 5% |
| all | 55% | 81% | 57 | 8% |

Low opening/endgame agreement with near-zero median loss reflects many equally good moves there; the real weakness
is tactics needing more than ~4 plies (17% blunders).

**Playing strength** (`elo_match.md`, games in `elo_match.pgn`): 48 games at 0.5 s per move against Stockfish limited
by UCI_Elo — 84% against 1320, 81% against 1500, 41% against 1700. Maximum-likelihood estimate **≈1670 Elo
(95% interval 1550–1780)** on Stockfish's UCI_Elo scale at this time control, which is not a FIDE rating.

## 4. Deployment readiness (8.5)

`infrastructure/docker-compose.prod.yml` (PostgreSQL, backend, frontend), secrets only via an env file
(`infrastructure/.env.example`), migrations on start, non-root containers, healthchecks, JSON request logs with
request IDs, Prometheus metrics at `/metrics`, a job-queue limit (HTTP 429) to bound CPU on an API without accounts,
and an operations guide in `docs/DEPLOYMENT.md`. Verified locally without containers: the standalone frontend build
and the backend in production settings served a full analysis in Chrome, logs and metrics were emitted, and the queue
limit answered 429. **Not done:** Docker images were not built (Docker is not installed on the development machine),
nothing was published to a public host, and the CI workflow has not run on GitHub.

## 5. Roadmap "definition of success"

| # | Criterion | Status |
|---|---|---|
| 1 | Independently implemented engine | Met: no chess library in the app; python-chess and Stockfish only in tests/benchmarks |
| 2 | Rules and move generation pass reference tests | Met: perft, SAN cross-check |
| 3 | Search algorithms benchmarked | Met: E1–E7 (E8 advanced pruning not implemented) |
| 4 | Position evaluation reproducible | Met: deterministic, symmetric, breakdown inspectable |
| 5 | Tactical and strategic modules measurable | Met as regression metrics; independent accuracy still open |
| 6 | Explanations grounded in engine output | Met for rule-based; LLM path untested against the live API |
| 7 | Web application works end-to-end | Met locally (browser-driven); not publicly deployed |
| 8 | Findings documented and reproducible | Met: scripts, datasets, seeds and reports in `research/` |

## 6. Limitations and next steps

1. **Search depth.** A native core (C++/Rust, bitboards) is the largest lever: 27× node rate plus deeper pruning
   (E8: null move, LMR, PVS, aspiration windows) would fix most tactical blunders.
2. **Independent evaluation.** Score the tactical detectors on an external themed puzzle set, and explanations with
   human raters (clarity, strategic relevance) plus a live Claude grounding run.
3. **Evaluation tuning.** Weights are hand-set; Texel-style tuning on labelled positions is the standard next step.
4. **Product.** Accounts/auth, rate limiting per client, shared engine defaults across processes, progress percentages
   for long analyses, rule-based explanations in languages other than English.
