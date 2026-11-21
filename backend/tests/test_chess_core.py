import pytest

from app.chess_core import START_FEN, FenError, Position, perft, validate_fen

# Reference counts: https://www.chessprogramming.org/Perft_Results
PERFT = [
    (START_FEN, [20, 400, 8902]),
    ("r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1", [48, 2039, 97862]),  # kiwipete
    ("8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1", [14, 191, 2812, 43238]),
    ("r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1", [6, 264, 9467]),
    ("rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8", [44, 1486, 62379]),
    # Variant of CPW position 6; counts generated with python-chess (reference library, test-only).
    ("r4rk1/1pp1qppp/p1np1n2/2b1p1B1/2B1P1b1/P1NP1N1P/1PP1QPP1/R4RK1 w - - 0 10", [48, 2166, 97403]),
]


@pytest.mark.parametrize("fen,counts", PERFT)
def test_perft(fen, counts):
    pos = Position(fen)
    for depth, expected in enumerate(counts, 1):
        assert perft(pos, depth) == expected, f"depth {depth}"
    assert pos.fen() == Position(fen).fen()  # make/unmake fully restores state


@pytest.mark.parametrize("fen", [f for f, _ in PERFT] + ["8/8/8/3pP3/8/8/8/k6K w - d6 0 3"])
def test_fen_round_trip(fen):
    assert Position(fen).fen() == fen


def test_castling_through_check_forbidden():
    pos = Position("r3k2r/8/8/8/8/8/5r2/R3K2R w KQkq - 0 1")  # black rook on f2 covers f1
    moves = {m.uci for m in pos.legal_moves()}
    assert "e1g1" not in moves and "e1c1" in moves


def test_en_passant_capture_and_undo():
    pos = Position("8/8/8/3pP3/8/8/8/k6K w - d6 0 3")
    before = pos.fen()
    pos.make(pos.parse_uci("e5d6"))
    assert pos.fen() == "8/8/3P4/8/8/8/8/k6K b - - 0 3"
    pos.unmake()
    assert pos.fen() == before


def test_promotion():
    pos = Position("8/P7/8/8/8/8/8/k6K w - - 0 1")
    assert {m.uci for m in pos.legal_moves() if m.frm == 96} == {"a7a8q", "a7a8r", "a7a8b", "a7a8n"}
    pos.make(pos.parse_uci("a7a8n"))
    assert pos.fen().startswith("N7/")


def test_game_states():
    assert Position("7k/6Q1/6K1/8/8/8/8/8 b - - 0 1").status() == "checkmate"
    assert Position("7k/8/6QK/8/8/8/8/8 b - - 0 1").status() == "stalemate"
    assert Position("8/8/8/4k3/8/8/2B5/4K3 w - - 0 1").status() == "insufficient_material"
    assert Position("8/8/8/4k3/8/8/8/R3K3 w - - 100 80").status() == "fifty_move"
    pos = Position(START_FEN)
    for uci in ["g1f3", "g8f6", "f3g1", "f6g8"] * 2:
        pos.make(pos.parse_uci(uci))
    assert pos.status() == "threefold_repetition"


@pytest.mark.parametrize("fen", ["", "8/8/8 w - - 0 1", "9/8/8/8/8/8/8/8 w - - 0 1",
                                 "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR x KQkq - 0 1"])
def test_bad_fen_syntax(fen):
    with pytest.raises(FenError):
        Position(fen)
    assert validate_fen(fen)["syntax_valid"] is False


@pytest.mark.parametrize("fen,error", [
    ("8/8/8/8/8/8/8/K7 w - - 0 1", "black must have exactly one king"),
    ("kk6/8/8/8/8/8/8/K7 w - - 0 1", "black must have exactly one king"),
    ("k7/8/8/8/8/8/8/K6P w - - 0 1", "pawn on back rank"),
    ("k7/8/8/8/8/8/8/K6r b - - 0 1", "side not to move is in check"),
    ("k7/8/8/8/8/8/8/K7 w K - 0 1", "castling right K"),
    ("k7/8/8/8/8/8/8/K7 w - e6 0 1", "inconsistent en passant"),
])
def test_illegal_positions(fen, error):
    result = validate_fen(fen)
    assert result["syntax_valid"] and not result["legal"]
    assert any(error in e for e in result["errors"]), result["errors"]


def test_legal_position_reports_moves():
    r = validate_fen(START_FEN)
    assert r["legal"] and r["status"] == "ongoing" and len(r["legal_moves"]) == 20


def test_castling_rights_are_per_side():
    pos = Position("r3k2r/8/8/8/8/8/8/R3K2R b Kq - 0 1")  # black may only castle queenside
    assert {m.uci for m in pos.legal_moves() if m.frm == 116 and abs(m.to - m.frm) == 2} == {"e8c8"}


def _walk_hashes(pos, depth):
    assert pos.hash == pos.full_hash(), pos.fen()
    if depth:
        for m in pos.legal_moves():
            pos.make(m)
            _walk_hashes(pos, depth - 1)
            pos.unmake()


@pytest.mark.parametrize("fen", [f for f, _ in PERFT[:5]])
def test_incremental_zobrist_matches_full(fen):
    pos = Position(fen)
    h = pos.hash
    _walk_hashes(pos, 2)
    assert pos.hash == h
