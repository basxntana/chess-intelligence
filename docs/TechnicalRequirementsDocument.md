**CHESS INTELLIGENCE**

Technical Requirements Document (TRD)

Version: 1.0 **Architecture:** Modular Monolith with Isolated Engine
Process **Backend:** Python + FastAPI **Frontend:** Next.js +
TypeScript **Database:** PostgreSQL

**1. Technical Architecture**

1.1 Architecture Overview

The application consists of five primary layers:

1.  Presentation Layer

2.  Application/API Layer

3.  Chess Engine Layer

4.  Intelligence and Explanation Layer

5.  Persistence Layer

**1.2 System Components**

Frontend

- Next.js

- React

- TypeScript

- Chessground

- Zustand or React Context

- TanStack Query

**Backend**

- Python

- FastAPI

- Pydantic

- SQLAlchemy

- Alembic

**Chess Engine**

- Python baseline implementation

- Optional C++ or Rust optimization

- Custom UCI-compatible engine interface

**Analysis**

- NumPy

- Rule-based tactical detection

- Strategic feature extraction

- Hybrid explanation service

**Infrastructure**

- PostgreSQL

- Redis (optional)

- Docker

- Pytest

- GitHub Actions

**2. Custom Chess Engine Requirements**

The engine is the core research component.

**2.1 Board Representation**

Initial implementation should use a 0x88 board representation.\
Requirements:

- Represent all 64 valid squares.

- Support all six chess piece types.

- Track piece color.

- Track active player.

- Track castling rights.

- Track en passant square.

- Track halfmove and fullmove counters.

The implementation should provide reversible state transitions.\
Alternative representations such as bitboards can be investigated as a
performance optimization.

**2.2 Move Generation**

The move generator must support:

- Pawn movement.

- Pawn promotion.

- En passant.

- Knight movement.

- Bishop movement.

- Rook movement.

- Queen movement.

- King movement.

- Castling.

- Check detection.

- Legal move filtering.

Pseudo-legal moves must be filtered to prevent moves that leave the
moving side's king in check.

**2.3 Search Algorithm**

The first engine version should implement:

**A. Minimax**\
Establish a basic recursive decision-making baseline.\
**B. Negamax**\
Simplify the search implementation using the zero-sum nature of chess.\
**C. Alpha-Beta Pruning**\
Reduce the number of nodes evaluated.\
**D. Iterative Deepening**\
Search progressively deeper until the time or depth limit is reached.\
**E. Move Ordering**\
Prioritize promising moves through:

- Principal variation move.

- Captures.

- Promotions.

- Killer moves.

- History heuristic.

**F. Quiescence Search**\
Extend evaluation in tactical positions to reduce horizon effects.

**2.4 Search Optimization**

Later implementations should investigate:

- Transposition tables.

- Zobrist hashing.

- Null-move pruning.

- Late move reductions.

- Aspiration windows.

- Principal variation search.

Each optimization must be independently benchmarked to measure its
effect on search performance and move quality.

**2.5 Evaluation Function**

The baseline evaluation function should use a weighted feature model.\
Example:\
Evaluation(Position) =

- Material Score

- 

  - Piece-Square Score

<!-- -->

- 

  - Mobility Score

<!-- -->

- 

  - Center Control Score

<!-- -->

- 

  - Pawn Structure Score

<!-- -->

- 

  - King Safety Score

<!-- -->

- 

  - Piece Coordination Score

The evaluation must be calculated from a consistent perspective,
preferably White's perspective internally, with sign conversion handled
by the search layer.\
Initial material values can use conventional centipawn values:

|           |                                      |
|-----------|--------------------------------------|
| **Piece** | Initial Value                        |
| Pawn      | 100                                  |
| Knight    | 320                                  |
| Bishop    | 330                                  |
| Rook      | 500                                  |
| Queen     | 900                                  |
| King      | Not assigned a normal material value |

These values are initial parameters, not universal chess truths.

**2.6 Endgame Handling**

The engine must distinguish:

- Checkmate.

- Stalemate.

- Insufficient material.

- Draw by repetition.

- Fifty-move rule.

Draw handling must be tested separately from the evaluation function.

**3. Position Intelligence Module**

This module extracts information from the board independently of the
search algorithm.

**3.1 Material Analysis**

Calculate:

- Total material by color.

- Material difference.

- Piece count.

- Material imbalance.

**3.2 Tactical Detection**

Initial tactical detectors:

**Fork**

- A piece attacks multiple valuable enemy targets.

**Pin**

- A piece cannot move without exposing a more valuable piece or king.

**Skewer**

- A valuable piece is attacked and must move, exposing another piece.

**Hanging Piece**

- A piece is undefended or insufficiently defended against a credible
  attack.

**Discovered Attack**

- Moving one piece reveals an attack from another piece.

**Double Attack**

- A move creates multiple simultaneous threats.

Important: Tactical motifs are contextual. Detection should consider
legal responses, exchanges, and move sequences, not only geometric
attack relationships.

**3.3 Strategic Feature Extraction**

Features include:

- King exposure.

- Open and semi-open files.

- Pawn islands.

- Doubled pawns.

- Isolated pawns.

- Passed pawns.

- Outposts.

- Piece mobility.

- Center occupancy and control.

Every feature should include:

- Feature name.

- Relevant squares or pieces.

- Side affected.

- Severity or numerical score.

- Supporting evidence.

**4. Hybrid Explanation Engine**

4.1 Architecture

The explanation system contains two reasoning components.

**Rule-Based Explanation**\
Uses structured facts from the engine and position analyzer.\
Example:

- The move develops a knight.

- The move attacks a central square.

- The move creates a threat against an opponent piece.

**LLM Explanation**\
Transforms verified facts into natural-language explanations.\
The LLM must receive:

- Current FEN.

- Selected move.

- Engine evaluation.

- Principal variation.

- Tactical features.

- Strategic features.

- Candidate move comparisons.

**4.2 Grounding Requirements**

The LLM must not:

- Invent legal moves.

- Change engine evaluation scores.

- Claim an unverified tactical motif.

- Present hypothetical variations as guaranteed outcomes.

- Claim checkmate without engine verification.

All generated statements should be traceable to engine output or
validated analysis features.\
If the LLM is unavailable, the rule-based explanation must remain
operational.

**5. Frontend Requirements**

5.1 Chessboard

- Interactive board.

- Drag-and-drop.

- Click-to-move.

- Manual piece placement.

- Legal move highlighting.

- Board orientation.

- FEN input.

- Reset position.

**5.2 Analysis Dashboard**

Display:

- Current evaluation.

- Recommended move.

- Candidate moves.

- Search depth.

- Search time.

- Principal variation.

- Tactical insights.

- Strategic insights.

**5.3 Move Explorer**

Users can:

- Explore candidate variations.

- Navigate forward and backward.

- Compare alternative moves.

- Return to the original position.

**5.4 Analysis History**

Users can:

- Save an analysis.

- Rename an analysis.

- Reopen an analysis.

- Delete an analysis.

**6. Backend API Requirements**

Position APIs

POST `/api/v1/positions/validate`\
POST `/api/v1/positions/fen`

**Analysis APIs**

POST `/api/v1/analysis`\
GET `/api/v1/analysis/``{``analysis_id``}`\
GET `/api/v1/analysis/``{``analysis_id``}``/variations`\
POST `/api/v1/analysis/``{``analysis_id``}``/explain`

**History APIs**

GET `/api/v1/history`\
GET `/api/v1/history/``{``analysis_id``}`\
DELETE `/api/v1/history/``{``analysis_id``}`

**Engine APIs**

GET `/api/v1/engine/status`\
GET `/api/v1/engine/config`\
PUT `/api/v1/engine/config`\
The analysis endpoint should support configurable depth, time limit, and
candidate count.\
Long-running analysis should use background jobs or an asynchronous
execution model. The frontend should receive progress information
through polling or WebSocket updates.

**7. Database Requirements**

Table: users

- id

- email

- password_hash

- created_at

**Table: positions**

- id

- user_id

- fen

- name

- created_at

**Table: analyses**

- id

- position_id

- engine_version

- search_depth

- time_limit

- evaluation_score

- best_move

- principal_variation

- analysis_status

- created_at

**Table: analysis_features**

- id

- analysis_id

- feature_type

- side

- description

- evidence

- severity

**Table: explanations**

- id

- analysis_id

- explanation_type

- explanation_content

- model_version

- created_at

Store engine configuration and version alongside results to make
experiments reproducible.

**8. Testing Requirements**

Unit Testing

- Board initialization.

- FEN parsing.

- Move generation.

- Legal move validation.

- Make and unmake move.

- Check detection.

- Castling.

- En passant.

- Promotion.

- Evaluation function.

- Search algorithm.

**Integration Testing**

- Frontend to backend.

- Backend to custom engine.

- Analysis to tactical detection.

- Analysis to explanation service.

- Database persistence.

**Engine Testing**

Use established chess test suites and perft positions.\
Required tests:

- Perft correctness.

- Known tactical positions.

- Checkmate positions.

- Stalemate positions.

- Endgame positions.

- Search consistency.

**Performance Testing**

Measure:

- Nodes per second.

- Search depth.

- Total nodes searched.

- Time per position.

- Memory consumption.

- Transposition table hit rate.

**9. Research Benchmarking**

Stockfish may be used as an external reference engine for benchmarking
only.\
It must not provide the actual recommendations returned by the custom
engine.\
Experiments should compare:

1.  Baseline minimax.

2.  Negamax.

3.  Alpha-Beta pruning.

4.  Alpha-Beta with move ordering.

5.  Alpha-Beta with transposition table.

6.  Optimized search with quiescence and iterative deepening.

**Evaluation Metrics**

|                       |                                           |
|-----------------------|-------------------------------------------|
| Metric                | Purpose                                   |
| Nodes per second      | Search throughput                         |
| Search depth          | Search capability                         |
| Node count            | Search efficiency                         |
| Best-move agreement   | Agreement with reference engine           |
| Tactical accuracy     | Performance on tactical test positions    |
| Elo estimate          | Playing strength under controlled testing |
| Feature F1-score      | Tactical detection quality                |
| Explanation grounding | Factual support of explanations           |

Elo testing must use controlled matches, fixed time controls, and an
appropriate rating-estimation method.

**10. Engineering Constraints**

- No external engine may generate production recommendations.

- Engine logic must be independently implemented.

- Reference libraries may be used for validation and testing.

- All engine decisions must be reproducible.

- Search optimizations must be benchmarked.

- LLM explanations must be grounded.

- Engine and API failures must be handled gracefully.

- Every important algorithm must have automated tests.

**11. Definition of Done**

A technical module is complete when:

1.  Its implementation is documented.

2.  Unit tests pass.

3.  Integration tests pass where applicable.

4.  Edge cases are handled.

5.  Performance is measured.

6.  Research assumptions are documented.

7.  Changes are committed to version control.
