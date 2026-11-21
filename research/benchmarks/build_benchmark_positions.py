"""Phase 8.1: build the engine benchmark position set, labelled by Stockfish (reference only).

Categories (seeded, reproducible):
  opening    - 4-12 plies into common openings, varied with Stockfish top-3 choices
  random     - random legal play, 10-60 plies (the roadmap's "random legal positions")
  tactical   - positions from imperfect Stockfish self-play where the best move beats the second best by >= 200 cp
               and wins (>= +100 cp): "only move" tactics
  endgame    - random legal endgames: both kings + 1-4 other men
Each position is labelled with Stockfish's best move, top-3 moves and evaluation at LABEL_DEPTH.

Usage (repo root): backend/.venv/bin/python research/benchmarks/build_benchmark_positions.py
Writes research/datasets/benchmark_positions.json.
"""
import json
import random
import shutil
from pathlib import Path

import chess
import chess.engine

ROOT = Path(__file__).resolve().parents[2]
SEED, LABEL_DEPTH, SCAN_DEPTH = 2026, 18, 10
COUNTS = {"opening": 40, "random": 40, "tactical": 60, "endgame": 40}
OPENINGS = [
    "e2e4 e7e5 g1f3 b8c6", "d2d4 d7d5 c2c4 e7e6", "e2e4 c7c5 g1f3 d7d6", "e2e4 e7e6 d2d4 d7d5",
    "e2e4 c7c6 d2d4 d7d5", "d2d4 g8f6 c2c4 g7g6", "c2c4 e7e5 b1c3 g8f6", "g1f3 d7d5 g2g3 g8f6",
]


def cp(score: chess.engine.PovScore, turn: chess.Color) -> int:
    return score.pov(turn).score(mate_score=100_000)


def label(engine, board: chess.Board) -> dict:
    infos = engine.analyse(board, chess.engine.Limit(depth=LABEL_DEPTH), multipv=3)
    top = [(i["pv"][0].uci(), cp(i["score"], board.turn)) for i in infos if i.get("pv")]
    return {"fen": board.fen(), "best_move": top[0][0], "eval_cp": top[0][1],
            "top3": [m for m, _ in top], "top3_cp": [s for _, s in top]}


def openings(engine, rng) -> list[chess.Board]:
    out = []
    while len(out) < COUNTS["opening"] * 2:
        board = chess.Board()
        for u in rng.choice(OPENINGS).split():
            board.push_uci(u)
        for _ in range(rng.randint(0, 8)):
            infos = engine.analyse(board, chess.engine.Limit(depth=8), multipv=3)
            board.push(rng.choice([i["pv"][0] for i in infos if i.get("pv")]))
        if not board.is_game_over():
            out.append(board)
    return out


def random_play(rng) -> list[chess.Board]:
    out = []
    while len(out) < COUNTS["random"] * 2:
        board = chess.Board()
        for _ in range(rng.randint(10, 60)):
            if board.is_game_over():
                break
            board.push(rng.choice(list(board.legal_moves)))
        if not board.is_game_over():
            out.append(board)
    return out


def tactical(engine, rng) -> list[chess.Board]:
    found: list[chess.Board] = []
    while len(found) < COUNTS["tactical"] * 2:
        board = chess.Board()
        for u in rng.choice(OPENINGS).split():
            board.push_uci(u)
        while not board.is_game_over() and board.ply() < 140:
            infos = engine.analyse(board, chess.engine.Limit(depth=SCAN_DEPTH), multipv=2)
            if len(infos) == 2:
                best, second = cp(infos[0]["score"], board.turn), cp(infos[1]["score"], board.turn)
                if best >= 100 and best - second >= 200 and abs(best) < 50_000:
                    found.append(board.copy())
            # Imperfect play (random among top 3 at low depth) creates the mistakes that tactics punish.
            infos = engine.analyse(board, chess.engine.Limit(depth=4), multipv=3)
            board.push(rng.choice([i["pv"][0] for i in infos if i.get("pv")]))
    return found


def endgames(rng) -> list[chess.Board]:
    out = []
    pieces = "PPPPNBRQ"
    while len(out) < COUNTS["endgame"] * 2:
        board = chess.Board(None)
        squares = rng.sample(list(chess.SQUARES), 6)
        board.set_piece_at(squares[0], chess.Piece(chess.KING, chess.WHITE))
        board.set_piece_at(squares[1], chess.Piece(chess.KING, chess.BLACK))
        for sq in squares[2:2 + rng.randint(1, 4)]:
            symbol = rng.choice(pieces)
            if symbol == "P" and chess.square_rank(sq) in (0, 7):
                continue
            board.set_piece_at(sq, chess.Piece.from_symbol(symbol if rng.random() < 0.5 else symbol.lower()))
        board.turn = rng.choice([chess.WHITE, chess.BLACK])
        if board.is_valid() and not board.is_game_over():
            out.append(board)
    return out


def main() -> None:
    rng = random.Random(SEED)
    engine = chess.engine.SimpleEngine.popen_uci(shutil.which("stockfish"))
    engine.configure({"Threads": 1, "Hash": 64})
    version = engine.id.get("name")
    pools = {"opening": openings(engine, rng), "random": random_play(rng), "tactical": tactical(engine, rng),
             "endgame": endgames(rng)}
    positions, seen = [], set()
    for category, boards in pools.items():
        rng.shuffle(boards)
        kept = 0
        for board in boards:
            key = board.board_fen() + (" w" if board.turn else " b")
            if key in seen or kept >= COUNTS[category]:
                continue
            row = label(engine, board)
            if category == "tactical" and (row["eval_cp"] < 100 or len(row["top3_cp"]) < 2
                                           or row["top3_cp"][0] - row["top3_cp"][1] < 200):
                continue  # did not survive the deeper look
            seen.add(key)
            kept += 1
            positions.append({"id": f"{category}-{kept:03d}", "category": category, **row})
        print(category, kept)
    engine.quit()
    out = ROOT / "research" / "datasets" / "benchmark_positions.json"
    out.write_text(json.dumps({"reference": version, "label_depth": LABEL_DEPTH, "seed": SEED,
                               "positions": positions}, indent=1))
    print(f"wrote {len(positions)} positions to {out}")


if __name__ == "__main__":
    main()
