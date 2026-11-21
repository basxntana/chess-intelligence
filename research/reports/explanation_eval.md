# Phase 8: explanation quality evaluation

Rule-based explanations of the engine's recommended move for 180 benchmark positions (analysis depth 4). Independent checks: python-chess for legality and checkmate, Stockfish depth 16 for mates, material/tactical claims and evaluations.

| Criterion (roadmap 8.4) | Measure | Result |
|---|---|---|
| Factual correctness | sentences passing grounding validation | 100% of 1622 |
| Factual correctness | "is checkmate" claims true (python-chess) | – (none made) |
| Factual correctness | "forced mate in N" confirmed by Stockfish | 5/5 (100%) |
| Move consistency | summary names the recommended move | 100% |
| Move consistency | recommended move legal (python-chess) | 100% |
| Tactical accuracy | "wins about X pawns" claims: Stockfish's line also wins ≥ 1 pawn | 77/88 (88%) |
| Tactical accuracy | stated evaluation has Stockfish's sign (when \|SF\| ≥ 50) | 94% |
| Tactical accuracy | median \|our eval − Stockfish eval\| (cp, clipped ±1000) | 111 |
| Readability (descriptive) | sentences per explanation / words per sentence / Flesch | 9.0 / 8.7 / 78 |
| Strategic relevance, human readability | — | needs human raters (not measured) |

## Material claims Stockfish did not confirm

- `opening-027` dxc4: Stockfish line material +0, eval -29 cp, loss 12 cp — "dxc4 is the engine's choice at depth 4, with an evaluation of -0.34 pawns for Black."
- `random-014` hxg4: Stockfish line material -900, eval +102 cp, loss 23 cp — "hxg4 is the engine's choice at depth 4, with an evaluation of +1.75 pawns for Black."
- `random-015` Bxd7+: Stockfish line material -150, eval +644 cp, loss 19 cp — "Bxd7+ is the engine's choice at depth 4, with an evaluation of +3.38 pawns for White."
- `random-020` bxc4: Stockfish line material +50, eval +577 cp, loss 1 cp — "bxc4 is the engine's choice at depth 4, with an evaluation of +3.99 pawns for White."
- `tactical-003` Nxc3: Stockfish line material +80, eval +852 cp, loss 0 cp — "Nxc3 is the engine's choice at depth 4, with an evaluation of +6.10 pawns for White."
- `tactical-019` Qxe8: Stockfish line material +0, eval +581 cp, loss 5 cp — "Qxe8 is the engine's choice at depth 4, with an evaluation of +1.71 pawns for Black."
- `tactical-026` exd3: Stockfish line material +70, eval +332 cp, loss 0 cp — "exd3 is the engine's choice at depth 4, with an evaluation of +1.45 pawns for Black."
- `tactical-035` a3: Stockfish line material -190, eval +517 cp, loss 0 cp — "a3 is the engine's choice at depth 4, with an evaluation of +1.42 pawns for White."
- `tactical-046` bxc6: Stockfish line material +0, eval +256 cp, loss 0 cp — "bxc6 is the engine's choice at depth 4, with an evaluation of -1.12 pawns for Black."
- `tactical-048` Ng6+: Stockfish line material +0, eval +99995 cp, loss 0 cp — "Ng6+ is the engine's choice at depth 4, with an evaluation of -1.36 pawns for White."
- `endgame-028` Bc5+: Stockfish line material -330, eval -99994 cp, loss 4 cp — "Bc5+ is the engine's choice at depth 4, with an evaluation of -6.18 pawns for White."

Grounding checks that each sentence matches the engine's own facts; the Stockfish checks measure whether those facts are right. Since every sentence passed grounding, any unconfirmed claim traces back to the engine's facts (depth 4 search), not to the explanation layer.
