# Chess Intelligence

Research-oriented chess analysis platform with a custom engine. See `docs/` for PRD, TRD and roadmap.

## Status

| Phase | State |
|---|---|
| 1. Foundation | Done: FastAPI backend, Next.js frontend, Docker Compose, CI |
| 2. Chess core | Done: 0x88 board, FEN, legal moves, make/unmake, draw rules, position validator; perft verified |
| 3. Search engine | Done: minimax, negamax, alpha-beta, move ordering (TT/MVV-LVA/killer/history), iterative deepening, quiescence, Zobrist + transposition table, multi-PV, time limits. Experiments E1–E7 in `research/reports/search_experiments.md`. Not done (E8): aspiration windows, PVS, null-move pruning, LMR |
| 4. Evaluation | Done: tapered (middlegame/endgame) weighted model: material, piece-square tables, mobility, center control, pawn structure (doubled/isolated/passed/connected/islands), king safety (shield, open files, king-zone attacks), bishop pair, rooks on open files. `explain()` gives per-term contributions + board evidence. Curated dataset `research/datasets/eval_pairs.json`; self-play calibration in `research/reports/eval_experiments.md`. Not done: automated parameter tuning |
| 5. Intelligence | Done: tactical detectors (fork, pin, skewer, hanging piece, discovered attack, double attack, checkmate threat, check/mate) with static exchange evaluation and engine verification of material-winning motifs; strategic features (material imbalance, piece activity, pawn weaknesses, passed pawns, open files, king safety, center); analysis pipeline per candidate move. Dataset `research/datasets/tactics.json`, report `research/reports/tactics_benchmark.md` |
| 6. Explanation | Done: verified fact list per move → rule-based explanation (always) + optional Claude explanation (`claude-opus-5-5`, structured JSON output, server-side refusal fallback). Every sentence cites fact ids; a grounding validator rejects unknown moves, squares, numbers, unsupported motifs/mate/material claims and guarantee language, and falls back to rule-based when the LLM is unavailable or ungrounded. SAN notation added |
| 7. Web app | Done: Chessground board (drag-drop, legal-move dots, position editor, FEN load, flip, promotion, undo), eval bar, candidate arrows, analysis/intelligence panels, move explorer, explanations (rule-based + Claude), history (rename/delete). Async analysis jobs in a process pool with polling; PostgreSQL via SQLAlchemy + Alembic |
| 8. Evaluation & deployment | Done: Stockfish-labelled benchmark (180 positions), engine-vs-reference metrics, Elo estimate (~1670 at 0.5 s/move vs Stockfish UCI_Elo), explanation evaluation, UCI interface (`python -m app.uci`), production compose, JSON logs, `/metrics`, queue limit. See `research/reports/FINAL_REPORT.md` and `docs/DEPLOYMENT.md` |

## Run locally

```bash
# database (PostgreSQL 16): Homebrew, or `docker compose -f infrastructure/docker-compose.yml up db`
brew services start postgresql@16
psql -d postgres -c "CREATE ROLE chess LOGIN PASSWORD 'chess'" \
  -c "CREATE DATABASE chess_intelligence OWNER chess" -c "CREATE DATABASE chess_intelligence_test OWNER chess"

# backend
cd backend
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/alembic upgrade head
.venv/bin/pytest -q                      # uses chess_intelligence_test (TEST_DATABASE_URL); never DATABASE_URL
.venv/bin/uvicorn app.main:app --port 8000   # http://localhost:8000/docs

# frontend
cd frontend && npm install && npm run dev  # http://localhost:3000
```

Config via env / `backend/.env`: `DATABASE_URL`, `CORS_ORIGINS`, `ANALYSIS_WORKERS` (default 2; 0 runs jobs inline),
`LLM_MODEL` (default `claude-opus-5-5`). LLM explanations need `ANTHROPIC_API_KEY`; without it the API returns the
rule-based explanation and says why. Frontend: `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`).

## API (`/api/v1`)

- `POST /positions/validate`, `POST /positions/fen`, `POST /positions/move` (apply a legal move; the UI has no chess rules)
- `POST /analysis` `{fen, depth?, time_limit?, candidates?, name?}` → job `{id, status}`; poll `GET /analysis/{id}` until `done`/`failed`.
  `result` holds search, evaluation breakdown, insights (tactics, strategic features, per-candidate changes), variations, explanation
- `GET /analysis/{id}/variations` (PVs with SAN + FEN per ply), `POST /analysis/{id}/explain` `{move?, use_llm?, language?}`
- `GET /history`, `GET /history/{id}`, `PATCH /history/{id}` `{name}`, `DELETE /history/{id}`, `DELETE /history` (clear all)
- `GET /engine/status`, `GET /engine/config`, `PUT /engine/config` (defaults for new analyses)
- `GET /health`

## Experiments

```bash
backend/.venv/bin/python research/benchmarks/search_experiments.py 3 4   # search techniques E1–E7, depths to run
backend/.venv/bin/python research/benchmarks/eval_experiments.py 3       # eval variants vs full eval (self-play)
backend/.venv/bin/python research/benchmarks/tactics_benchmark.py        # detector precision/recall + random-position checks
backend/.venv/bin/python research/benchmarks/explanation_live_check.py 10 # live Claude grounding check (costs API credits)
# Phase 8 (needs `brew install stockfish`; Stockfish is a yardstick only)
backend/.venv/bin/python research/benchmarks/build_benchmark_positions.py  # ~12 min, writes research/datasets/benchmark_positions.json
backend/.venv/bin/python research/benchmarks/engine_vs_stockfish.py 1.0 4  # agreement, centipawn loss, speed
backend/.venv/bin/python research/benchmarks/explanation_eval.py 4 4       # explanation claims vs python-chess/Stockfish
backend/.venv/bin/python research/benchmarks/elo_match.py 0.5 6 1320 1500 1700  # ~15 min, games as PGN
```

## Layout

`backend/app/chess_core` is the engine's rule layer (no external chess libs; `python-chess` is a test-only reference).
`search/` is the Phase 3 engine; `evaluation/` is the Phase 4 feature model. `intelligence/` is Phase 5 (tactics, strategy, pipeline). `chess_core/attacks.py` holds SEE. `explanation/` is Phase 6 (facts, rules, llm, grounding). `service.py` runs analysis jobs; `models.py` + `migrations/` are the database.
