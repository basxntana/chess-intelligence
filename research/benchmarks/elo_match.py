"""Phase 8.3: playing-strength estimate. Our engine (over UCI, `python -m app.uci`) plays Stockfish limited with
UCI_LimitStrength/UCI_Elo at several levels. Fixed time per move for both sides, every opening played with both
colors, games capped at MAX_PLIES (then scored a draw). Elo is the maximum-likelihood rating given the results and
the opponents' nominal UCI_Elo, with a 95% interval from the Fisher information.

Caveat: UCI_Elo is Stockfish's own calibration (anchored to CCRL-style ratings at long time controls), so the
estimate is only as good as that anchor at this time control.

Usage (repo root): backend/.venv/bin/python research/benchmarks/elo_match.py [seconds_per_move] [workers] [elo ...]
Writes research/reports/elo_match.{json,md} and the games as PGN.
"""
import json
import math
import shutil
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import chess
import chess.engine
import chess.pgn

ROOT = Path(__file__).resolve().parents[2]
OPENINGS = [
    "e2e4 e7e5 g1f3 b8c6", "d2d4 d7d5 c2c4 e7e6", "e2e4 c7c5 g1f3 d7d6", "e2e4 e7e6 d2d4 d7d5",
    "e2e4 c7c6 d2d4 d7d5", "d2d4 g8f6 c2c4 g7g6", "c2c4 e7e5 b1c3 g8f6", "g1f3 d7d5 g2g3 g8f6",
]
MAX_PLIES = 200


def play(args) -> dict:
    elo, opening_idx, ours_white, seconds = args
    ours = chess.engine.SimpleEngine.popen_uci([sys.executable, "-m", "app.uci"], cwd=ROOT / "backend")
    sf = chess.engine.SimpleEngine.popen_uci(shutil.which("stockfish"))
    sf.configure({"Threads": 1, "Hash": 16, "UCI_LimitStrength": True, "UCI_Elo": elo})
    board = chess.Board()
    for u in OPENINGS[opening_idx].split():
        board.push_uci(u)
    try:
        while not board.is_game_over(claim_draw=True) and board.ply() < MAX_PLIES:
            engine = ours if (board.turn == chess.WHITE) == ours_white else sf
            board.push(engine.play(board, chess.engine.Limit(time=seconds)).move)
    finally:
        ours.quit()
        sf.quit()
    outcome = board.outcome(claim_draw=True)
    if outcome is None or outcome.winner is None:
        score = 0.5
    else:
        score = 1.0 if outcome.winner == (chess.WHITE if ours_white else chess.BLACK) else 0.0
    game = chess.pgn.Game.from_board(board)
    game.headers.update({"White": "ChessIntelligence" if ours_white else f"Stockfish UCI_Elo {elo}",
                         "Black": f"Stockfish UCI_Elo {elo}" if ours_white else "ChessIntelligence",
                         "Event": f"Phase 8 Elo match, {seconds}s/move",
                         "Result": board.result(claim_draw=True) if outcome else "1/2-1/2"})
    return {"elo": elo, "opening": opening_idx, "ours_white": ours_white, "score": score, "plies": board.ply(),
            "termination": outcome.termination.name if outcome else "MAX_PLIES", "pgn": str(game)}


def expected(r: float, opp: float) -> float:
    return 1 / (1 + 10 ** ((opp - r) / 400))


def mle_elo(games: list[dict]) -> tuple[float, float, float]:
    """Rating R solving sum(score - E(R)) = 0, with a 95% interval; bounded to [0, 3500]."""
    lo, hi = 0.0, 3500.0
    for _ in range(100):
        mid = (lo + hi) / 2
        if sum(g["score"] - expected(mid, g["elo"]) for g in games) > 0:
            lo = mid
        else:
            hi = mid
    r = (lo + hi) / 2
    k = math.log(10) / 400
    info = sum(k * k * expected(r, g["elo"]) * (1 - expected(r, g["elo"])) for g in games)
    half = 1.96 / math.sqrt(info) if info > 0 else float("inf")
    return r, r - half, r + half


def main(seconds: float, workers: int, levels: list[int]) -> None:
    jobs = [(elo, i, white, seconds) for elo in levels for i in range(len(OPENINGS)) for white in (True, False)]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        games = list(ex.map(play, jobs))
    r, lo, hi = mle_elo(games)
    reports = ROOT / "research" / "reports"
    (reports / "elo_match.pgn").write_text("\n\n".join(g["pgn"] for g in games) + "\n")
    (reports / "elo_match.json").write_text(json.dumps(
        {"seconds_per_move": seconds, "levels": levels, "elo": r, "ci95": [lo, hi],
         "games": [{k: v for k, v in g.items() if k != "pgn"} for g in games]}, indent=1))
    md = ["# Phase 8: playing-strength estimate", "",
          (f"Custom engine (over UCI) vs Stockfish with UCI_LimitStrength, {seconds}s per move for both, "
           f"{len(OPENINGS)} openings × both colors per level, draw adjudicated at {MAX_PLIES} plies. "
           f"Games: `elo_match.pgn`."), "",
          "| Opponent UCI_Elo | Games | W-D-L | Score | Avg plies |", "|---:|---:|---|---:|---:|"]
    for elo in levels:
        g = [x for x in games if x["elo"] == elo]
        w, d, l_ = (sum(x["score"] == s for x in g) for s in (1, 0.5, 0))
        md.append(f"| {elo} | {len(g)} | {w}-{d}-{l_} | {sum(x['score'] for x in g) / len(g):.2f} | "
                  f"{sum(x['plies'] for x in g) / len(g):.0f} |")
    terms = {}
    for g in games:
        terms[g["termination"]] = terms.get(g["termination"], 0) + 1
    md += ["", (f"**Estimated rating: {r:.0f}** (95% interval {lo:.0f}–{hi:.0f}), maximum likelihood over all "
           f"{len(games)} games against the opponents' nominal UCI_Elo."), "",
           "Game endings: " + ", ".join(f"{k.lower()} {v}" for k, v in sorted(terms.items())) + ".", "",
           ("Caveats: UCI_Elo is Stockfish's own calibration at long time controls, not a FIDE rating; "
           "the interval reflects game count only, not anchor error. A score of 0 or 1 against every level "
           "means the rating lies outside the tested range and the estimate is a bound."), ""]
    (reports / "elo_match.md").write_text("\n".join(md))
    print("\n".join(md))


if __name__ == "__main__":
    a = sys.argv[1:]
    main(float(a[0]) if a else 0.5, int(a[1]) if len(a) > 1 else 6, [int(x) for x in a[2:]] or [1320, 1500, 1700])
