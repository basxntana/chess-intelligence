from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_validate_legal_and_illegal():
    ok = client.post("/api/v1/positions/validate", json={"fen": "8/8/8/8/8/8/8/K6k w - -"}).json()
    assert ok["legal"] and ok["fen"] == "8/8/8/8/8/8/8/K6k w - - 0 1"
    bad = client.post("/api/v1/positions/validate", json={"fen": "8/8/8/8/8/8/8/K7 w - - 0 1"}).json()
    assert bad["syntax_valid"] and not bad["legal"]


def test_validate_rejects_garbage():
    assert client.post("/api/v1/positions/validate", json={"fen": "x" * 500}).status_code == 422
    assert client.post("/api/v1/positions/fen", json={"fen": "hello"}).json()["syntax_valid"] is False


def test_analysis_returns_legal_best_move_and_candidates():
    resp = client.post("/api/v1/analysis", json={"fen": "6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1", "depth": 3})
    r = resp.json()
    assert resp.status_code == 201 and r["status"] == "done"  # inline run (ANALYSIS_WORKERS=0)
    assert r["best_move"] == "a1a8" and r["mate_in"] == 1 and r["result"]["search"]["best_move"] == "a1a8"
    assert r["engine_version"] and r["config"]["depth"] == 3 and r["depth"] == 3
    ev = r["result"]["evaluation"]
    assert set(ev["terms"]) >= {"material", "pst", "king_safety"} and ev["features"]


def test_analysis_rejects_illegal_position_and_bad_params():
    assert client.post("/api/v1/analysis", json={"fen": "8/8/8/8/8/8/8/K7 w - - 0 1"}).status_code == 422
    assert client.post("/api/v1/analysis", json={"fen": "8/8/8/8/8/8/8/K6k w - - 0 1", "depth": 99}).status_code == 422
