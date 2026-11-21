import io
import sys
from pathlib import Path

import chess
import chess.engine

from app.uci import main, time_budget


def run(lines: str) -> list[str]:
    out = io.StringIO()
    main(io.StringIO(lines), out)
    return out.getvalue().splitlines()


def test_handshake_and_mate_in_one():
    lines = run("uci\nisready\nposition fen 6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1\ngo depth 3\nquit\n")
    assert "uciok" in lines and "readyok" in lines
    assert lines[-1] == "bestmove a1a8" and "score mate 1" in lines[-2]


def test_position_with_moves_and_movetime():
    lines = run("position startpos moves e2e4 e7e5\ngo movetime 200\n")
    move = lines[-1].split()[1]
    board = chess.Board()
    board.push_uci("e2e4")
    board.push_uci("e7e5")
    assert chess.Move.from_uci(move) in board.legal_moves


def test_time_budget():
    assert time_budget({"movetime": 500}, True) == 0.5
    assert 0.05 <= time_budget({"wtime": 60000, "btime": 1000, "winc": 0}, True) <= 20
    assert time_budget({"wtime": 60000, "btime": 900}, False) <= 0.3
    assert time_budget({}, True) is None


def test_works_through_a_real_uci_client():
    """python-chess drives the engine over stdin/stdout like any GUI would."""
    backend = Path(__file__).parents[1]
    engine = chess.engine.SimpleEngine.popen_uci([sys.executable, "-m", "app.uci"], cwd=backend)
    try:
        board = chess.Board("r3k3/8/8/3N4/8/8/8/4K3 w - - 0 1")
        r = engine.play(board, chess.engine.Limit(time=0.5))
        assert r.move == chess.Move.from_uci("d5c7")
        info = engine.analyse(board, chess.engine.Limit(depth=3))
        assert info["score"].white().score() > 0
    finally:
        engine.quit()
