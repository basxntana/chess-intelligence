import json
import random
from pathlib import Path

import pytest

from app.chess_core import START_FEN, Position
from app.evaluation import DEFAULT, MATERIAL_ONLY, MAX_PHASE, TERMS, EvalConfig, evaluate, explain
from app.search import SearchConfig, search

PAIRS = json.loads((Path(__file__).parents[2] / "research" / "datasets" / "eval_pairs.json").read_text())
FENS = [
    START_FEN,
    "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
    "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1",
    "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1",
    "rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8",
]


def mirror(fen: str) -> str:
    """Swap colors and flip the board vertically: the evaluation must negate exactly."""
    placement, turn, castling, ep, half, full = fen.split()
    placement = "/".join(reversed(placement.split("/"))).swapcase()
    castling = "".join(sorted(castling.swapcase(), key="KQkq".index)) if castling != "-" else "-"
    ep = ep if ep == "-" else ep[0] + str(9 - int(ep[1]))
    return f"{placement} {'b' if turn == 'w' else 'w'} {castling} {ep} {half} {full}"


def random_positions(n: int, seed: int = 7) -> list[str]:
    rng, out = random.Random(seed), []
    while len(out) < n:
        pos = Position()
        for _ in range(rng.randint(4, 60)):
            moves = pos.legal_moves()
            if not moves:
                break
            pos.make(rng.choice(moves))
        out.append(pos.fen())
    return out


@pytest.mark.parametrize("pair", PAIRS, ids=[p["name"] for p in PAIRS])
def test_curated_pairs(pair):
    better, worse = evaluate(Position(pair["better"])), evaluate(Position(pair["worse"]))
    assert better > worse, f"{pair['principle']}: {better} <= {worse}"
    # Same judgement when colors are swapped (Black's view).
    assert evaluate(Position(mirror(pair["better"]))) < evaluate(Position(mirror(pair["worse"])))


@pytest.mark.parametrize("fen", FENS + random_positions(150))
def test_color_symmetry(fen):
    assert evaluate(Position(mirror(fen))) == -evaluate(Position(fen))


def test_start_position_is_balanced_and_full_phase():
    e = explain(Position(START_FEN))
    assert e["score"] == 0 and e["phase"] == MAX_PHASE


def test_score_ignores_side_to_move():
    fen = FENS[1]
    assert evaluate(Position(fen)) == evaluate(Position(fen.replace(" w ", " b ")))


def test_search_orientation_symmetric():
    for fen in FENS[:3]:
        a = search(Position(fen), SearchConfig(depth=2))
        b = search(Position(mirror(fen)), SearchConfig(depth=2))
        assert a.score == b.score and a.score_white == -b.score_white


@pytest.mark.parametrize("fen", FENS)
def test_terms_add_up_to_total(fen):
    e = explain(Position(fen))
    assert abs(sum(t["score"] for t in e["terms"].values()) - e["score"]) <= 1
    for t in e["terms"].values():
        assert abs(t["white"] - t["black"] - t["score"]) <= 0.2


def test_disabled_terms_contribute_nothing():
    e = explain(Position(FENS[1]), MATERIAL_ONLY)
    assert all(e["terms"][t]["score"] == 0 for t in TERMS if t != "material")
    assert evaluate(Position(FENS[1]), MATERIAL_ONLY) == 0


def test_tapering_moves_king_preference():
    # Same king squares, but with queens on the board the castled king wins; in a pawn ending the central one does.
    mg_safe = evaluate(Position("3qk3/8/8/8/8/8/5PPP/3Q2K1 w - - 0 1"))
    mg_center = evaluate(Position("3qk3/8/8/8/4K3/8/5PPP/3Q4 w - - 0 1"))
    eg_safe = evaluate(Position("4k3/8/8/8/8/8/5PPP/6K1 w - - 0 1"))
    eg_center = evaluate(Position("4k3/8/8/8/4K3/8/5PPP/8 w - - 0 1"))
    assert mg_safe > mg_center and eg_center > eg_safe
    static = EvalConfig(tapered=False)
    assert evaluate(Position("4k3/8/8/8/8/8/5PPP/6K1 w - - 0 1"), static) > \
        evaluate(Position("4k3/8/8/8/4K3/8/5PPP/8 w - - 0 1"), static)


def feats(fen: str, name: str, side: str = "white") -> list[dict]:
    return [f for f in explain(Position(fen))["features"] if f["feature"] == name and f["side"] == side]


def test_feature_evidence():
    assert feats("4k3/8/8/8/3P4/8/8/4K3 w - - 0 1", "isolated_pawn")[0]["squares"] == ["d4"]
    assert feats("4k3/8/8/8/8/2P5/2P5/4K3 w - - 0 1", "doubled_pawns")[0]["squares"] == ["c2", "c3"]
    passed = feats("4k3/p7/4P3/8/8/8/8/4K3 w - - 0 1", "passed_pawn")
    assert passed[0]["squares"] == ["e6"] and passed[0]["detail"]["relative_rank"] == 6
    assert not feats("4k3/3p4/8/4P3/8/8/8/4K3 w - - 0 1", "passed_pawn")  # d7 pawn guards e6
    assert feats("4k3/8/8/8/8/8/8/2B1KB2 w - - 0 1", "bishop_pair")[0]["squares"] == ["c1", "f1"]
    assert feats("3k4/1p4p1/8/8/8/8/1P4P1/3RK3 w - - 0 1", "rook_open_file")[0]["squares"] == ["d1"]
    shield = feats("4k3/8/8/8/8/8/5PPP/6K1 w - - 0 1", "pawn_shield")[0]
    assert shield["squares"] == ["f2", "g2", "h2"] and shield["mg"] == 36
    zone = feats("r1b1k2r/pppp1ppp/2n2n2/2b1p3/2B1P2q/2N2N2/PPPP1PPP/R1BQ1RK1 w kq - 0 1", "king_zone_attacked")
    assert zone and "f2" in zone[0]["squares"]
    open_files = feats("4k3/8/8/8/8/8/5P1P/6K1 w - - 0 1", "open_files_near_king")
    assert open_files[0]["detail"]["files"] == ["g"]


def test_default_config_is_reported():
    r = search(Position(START_FEN), SearchConfig(depth=1))
    assert r.config["eval"]["tapered"] is True and DEFAULT.tapered
