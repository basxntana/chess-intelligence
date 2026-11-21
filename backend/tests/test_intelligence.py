import pytest
from fastapi.testclient import TestClient

from app.chess_core import Position
from app.chess_core.attacks import see
from app.chess_core.board import parse_sq
from app.intelligence import analyze, position_tactics, strategic_features
from app.intelligence.benchmark import detect, load, run
from app.intelligence.strategy import feature_changes
from app.main import app
from app.search import SearchConfig

DATA = load()


def _see(fen: str, uci: str) -> int:
    b = Position(fen).board
    return see(b, parse_sq(uci[:2]), parse_sq(uci[2:4]))


def test_see():
    assert _see("4k3/8/8/4n3/8/8/8/4RK2 w - - 0 1", "e1e5") == 320  # undefended
    assert _see("4k3/8/3p4/4n3/8/8/8/4RK2 w - - 0 1", "e1e5") == -180  # RxN, pxR
    assert _see("4k3/8/5p2/4n3/3P4/8/8/4K3 w - - 0 1", "d4e5") == 220  # PxN, pxP
    # x-ray: the second rook behind joins the exchange
    assert _see("4k3/4r3/8/4p3/8/8/4R3/4R1K1 w - - 0 1", "e2e5") == 100
    # A king capture only pays if the square is not defended (the opponent king may not recapture into the queen).
    assert _see("8/8/8/8/8/8/4pk2/4K3 w - - 0 1", "e1e2") < 0
    assert _see("8/8/8/8/8/8/4pk2/3QK3 w - - 0 1", "e1e2") == 100


@pytest.mark.parametrize("case", DATA["cases"], ids=[c["id"] for c in DATA["cases"]])
def test_dataset_case(case):
    assert detect(case, DATA) == set(case["labels"])


def test_every_detector_has_positive_and_negative_cases():
    for motif in DATA["move_vocabulary"]:
        move_cases = [c for c in DATA["cases"] if c.get("move")]
        assert any(motif in c["labels"] for c in move_cases), motif
        assert any(motif not in c["labels"] for c in move_cases), motif


def test_benchmark_reports_metrics_and_errors():
    r = run()
    assert set(r["metrics"]) >= {"fork", "pin", "skewer", "hanging_piece", "checkmate_threat"}
    for m in r["metrics"].values():
        assert {"tp", "fp", "fn", "precision", "recall", "f1"} <= m.keys()
    assert all("false_positives" in c for c in r["cases"])


@pytest.mark.parametrize("fen", [c["fen"] for c in DATA["cases"]])
def test_findings_are_traceable(fen):
    pos = Position(fen)
    for f in position_tactics(pos):
        assert f["evidence"] and f["by"] in ("white", "black")
        if f["motif"] in ("hanging_piece", "pin", "skewer"):
            assert pos.board[parse_sq(f["squares"][0])] is not None  # names a real piece


def feats(fen, name, side=None):
    return [f for f in strategic_features(Position(fen)) if f["feature"] == name and (side is None or f["side"] == side)]


def test_strategic_features():
    assert feats("4k3/8/8/8/3P4/8/8/4K3 w - - 0 1", "isolated_pawn", "white")[0]["squares"] == ["d4"]
    assert feats("4k3/8/8/8/3P4/8/8/4K3 w - - 0 1", "passed_pawn", "white")
    open_files = {f["evidence"]["file"] for f in feats("4k3/8/8/8/8/8/PPP2PPP/4K3 w - - 0 1", "open_file")}
    assert open_files == {"d", "e"}
    assert feats("4k3/8/8/8/8/8/8/R3K3 w - - 0 1", "material_balance")[0]["score"] == 500
    assert feats("4k3/8/8/2n5/8/8/8/R3K3 w - - 0 1", "exchange_up", "white")
    passive = feats("4k3/8/8/8/8/8/PPP5/NB2K3 w - - 0 1", "passive_piece", "white")
    assert passive and passive[0]["evidence"]["moves"] <= 2
    for f in strategic_features(Position("r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1")):
        assert {"category", "feature", "side", "squares", "score", "evidence"} <= f.keys()


def test_feature_changes_capture_undoubles_pawns():
    pos = Position("4k3/8/8/8/3n4/2P5/2P5/4K3 w - - 0 1")
    before = strategic_features(pos)
    pos.make(pos.parse_uci("c3d4"))  # cxd4: c-pawns no longer doubled
    changes = feature_changes(before, strategic_features(pos))
    assert any(f["feature"] == "doubled_pawns" for f in changes["lost"])
    assert not any(f["feature"] == "doubled_pawns" for f in changes["gained"])


def test_pipeline_on_fork_position():
    out = analyze(Position("r3k3/8/8/3N4/8/8/8/4K3 w - - 0 1"), SearchConfig(depth=3, candidates=2))
    assert out["schema_version"] == 1 and out["side_to_move"] == "white"
    best = out["candidates"][0]
    assert best["move"] == "d5c7"
    assert any(t["motif"] == "fork" and t["verified"] for t in best["tactics"])
    assert set(best["eval_change"]) >= {"material", "king_safety"}
    assert {"gained", "lost"} == set(best["strategic_changes"])


def test_api_analysis_includes_insights():
    client = TestClient(app)
    r = client.post("/api/v1/analysis", json={"fen": "r3k3/8/8/3N4/8/8/8/4K3 w - - 0 1", "depth": 3}).json()
    assert r["best_move"] == "d5c7"
    insights = r["result"]["insights"]
    motifs = {t["motif"] for t in insights["candidates"][0]["tactics"]}
    assert {"check", "fork"} <= motifs
    assert "search" not in insights
