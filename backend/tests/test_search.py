import time

import pytest

from app.chess_core import START_FEN, Position
from app.evaluation import MATERIAL_ONLY
from app.search import SearchConfig, search

PLAIN = {"move_ordering": False, "iterative_deepening": False, "quiescence": False, "transposition_table": False}
POSITIONS = [
    START_FEN,
    "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
    "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1",
    "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1",
    "6k1/5ppp/8/8/8/8/5PPP/R5K1 b - - 0 1",
]


@pytest.mark.parametrize("fen", POSITIONS)
@pytest.mark.parametrize("depth", [1, 2, 3])
def test_pruning_and_ordering_preserve_minimax_value(fen, depth):
    """Alpha-beta (+ordering) must return exactly the exhaustive minimax root score."""
    ref = search(Position(fen), SearchConfig(depth=depth, algorithm="minimax", **PLAIN))
    for algorithm, ordering in (("negamax", False), ("alphabeta", False), ("alphabeta", True)):
        cfg = SearchConfig(depth=depth, algorithm=algorithm, **{**PLAIN, "move_ordering": ordering})
        r = search(Position(fen), cfg)
        assert r.score == ref.score, (algorithm, ordering)
        if algorithm != "minimax" and not ordering:
            assert r.nodes <= ref.nodes


def test_alphabeta_searches_fewer_nodes():
    fen = POSITIONS[1]
    mm = search(Position(fen), SearchConfig(depth=3, algorithm="negamax", **PLAIN))
    ab = search(Position(fen), SearchConfig(depth=3, **{**PLAIN, "move_ordering": True}))
    assert ab.nodes * 5 < mm.nodes


@pytest.mark.parametrize("fen,best,mate", [
    ("6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1", "a1a8", 1),  # back-rank mate
    ("r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4", "h5f7", 1),  # scholar's mate
    ("6k1/8/6K1/8/8/8/8/1R6 w - - 0 1", "b1b8", 1),
])
def test_finds_mate(fen, best, mate):
    r = search(Position(fen), SearchConfig(depth=4))
    assert r.best_move == best and r.mate_in == mate


def test_mate_in_two():
    # 1.Qg8+ Rxg8 2.Nf7# (smothered mate)
    pos = Position("r6k/6pp/7N/8/8/1Q6/8/6K1 w - - 0 1")
    r = search(pos, SearchConfig(depth=4))
    assert r.mate_in == 2 and len(r.pv) == 3
    for uci in r.pv:
        pos.make(pos.parse_uci(uci))
    assert pos.is_checkmate()


def test_quiescence_avoids_losing_capture():
    # Qxd5?? loses the queen to cxd5 (a pawn defends d5); without quiescence depth 1 grabs the pawn.
    fen = "4k3/8/2p5/3p4/8/8/8/3QK3 w - - 0 1"
    naive = search(Position(fen), SearchConfig(depth=1, quiescence=False))
    smart = search(Position(fen), SearchConfig(depth=1))
    assert naive.best_move == "d1d5" and smart.best_move != "d1d5"


def test_wins_hanging_queen():
    r = search(Position("4k3/8/8/3q4/8/8/8/3RK3 w - - 0 1"), SearchConfig(depth=2, eval=MATERIAL_ONLY))
    assert r.best_move == "d1d5" and r.score == 500  # rook vs nothing after Rxd5


def test_multipv_candidates_are_distinct_sorted_and_legal():
    pos = Position(POSITIONS[1])
    r = search(pos, SearchConfig(depth=3, candidates=3))
    legal = {m.uci for m in pos.legal_moves()}
    moves = [c.move for c in r.candidates]
    assert len(moves) == 3 == len(set(moves)) and set(moves) <= legal
    assert [c.score for c in r.candidates] == sorted((c.score for c in r.candidates), reverse=True)
    assert r.best_move == moves[0]


def test_multipv_scores_match_single_pv_searches():
    # each candidate's score must be exact: equal to searching that move alone
    fen = POSITIONS[1]
    r = search(Position(fen), SearchConfig(depth=2, candidates=3, **PLAIN))
    for c in r.candidates:
        pos = Position(fen)
        pos.make(pos.parse_uci(c.move))
        child = search(pos, SearchConfig(depth=1, **PLAIN))
        assert -child.score == c.score


def test_pv_is_legal_sequence():
    pos = Position(POSITIONS[1])
    r = search(pos, SearchConfig(depth=4))
    assert len(r.pv) >= 1
    for uci in r.pv:
        pos.make(pos.parse_uci(uci))  # raises if illegal


def test_reproducible_at_fixed_depth():
    a = search(Position(POSITIONS[1]), SearchConfig(depth=3, candidates=3))
    b = search(Position(POSITIONS[1]), SearchConfig(depth=3, candidates=3))
    assert (a.best_move, a.score, a.pv, a.nodes, a.candidates) == (b.best_move, b.score, b.pv, b.nodes, b.candidates)


def test_time_limit_respected_and_position_restored():
    pos = Position(POSITIONS[1])
    fen = pos.fen()
    t = time.perf_counter()
    r = search(pos, SearchConfig(depth=30, time_limit=0.3))
    assert time.perf_counter() - t < 1.5
    assert 1 <= r.depth < 30 and r.best_move in {m.uci for m in pos.legal_moves()}
    assert pos.fen() == fen and pos.hash == pos.full_hash()


def test_terminal_root_positions():
    mated = search(Position("7k/6Q1/6K1/8/8/8/8/8 b - - 0 1"))
    assert mated.best_move is None and mated.terminal == "checkmate"
    stale = search(Position("7k/8/6QK/8/8/8/8/8 b - - 0 1"))
    assert stale.best_move is None and stale.terminal == "stalemate" and stale.score == 0


def test_black_to_move_score_orientation():
    # Black is a queen up and to move: positive for side to move, negative from White's view.
    r = search(Position("4k3/8/8/3q4/8/8/8/4K3 b - - 0 1"), SearchConfig(depth=2))
    assert r.score > 800 and r.score_white < -800
