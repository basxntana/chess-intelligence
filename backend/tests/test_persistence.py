import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import main, service
from app.chess_core import Position
from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import AnalysisFeatureRow, AnalysisRow, ExplanationRow, PositionRow

client = TestClient(app)
FORK = "r3k3/8/8/3N4/8/8/8/4K3 w - - 0 1"
START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def create(fen=FORK, **kw):
    r = client.post("/api/v1/analysis", json={"fen": fen, "depth": 2, **kw})
    assert r.status_code in (201, 202), r.text
    return r.json()


def count(model, **where):
    with SessionLocal() as db:
        q = select(func.count()).select_from(model)
        for k, v in where.items():
            q = q.where(getattr(model, k) == v)
        return db.scalar(q)


def test_analysis_lifecycle_and_storage():
    a = create(name="Knight fork")
    assert a["status"] == "done" and a["name"] == "Knight fork" and a["best_move"] == "d5c7"
    assert a["engine_version"] == settings.engine_version and a["config"]["depth"] == 2  # reproducibility
    aid = uuid.UUID(a["id"])
    assert count(AnalysisFeatureRow, analysis_id=aid) > 0
    assert count(ExplanationRow, analysis_id=aid) == 1
    assert client.get(f"/api/v1/analysis/{a['id']}").json()["result"]["search"]["best_move"] == "d5c7"

    client.post(f"/api/v1/analysis/{a['id']}/explain", json={})
    assert count(ExplanationRow, analysis_id=aid) == 2


def test_variations_replay_to_their_fens():
    a = create(candidates=2)
    v = client.get(f"/api/v1/analysis/{a['id']}/variations").json()
    assert len(v["variations"]) == 2
    for var in v["variations"]:
        pos = Position(v["fen"])
        assert var["plies"][0]["uci"] == var["move"]
        for ply in var["plies"]:
            pos.make(pos.parse_uci(ply["uci"]))
            assert pos.fen() == ply["fen"]
    assert v["variations"][0]["plies"][0]["san"] == "Nc7+"


def test_history_rename_delete():
    a, b = create(name="first"), create(fen=START, name="second")
    items = client.get("/api/v1/history").json()["items"]
    ids = [i["id"] for i in items]
    assert ids.index(b["id"]) < ids.index(a["id"])  # newest first
    assert "result" not in items[0]  # list view stays light

    r = client.patch(f"/api/v1/history/{a['id']}", json={"name": "  renamed  "})
    assert r.json()["name"] == "renamed"
    assert client.patch(f"/api/v1/history/{a['id']}", json={"name": ""}).status_code == 422

    assert client.delete(f"/api/v1/history/{a['id']}").status_code == 204
    assert client.get(f"/api/v1/history/{a['id']}").status_code == 404
    assert count(ExplanationRow, analysis_id=uuid.UUID(a["id"])) == 0  # cascaded
    assert client.delete(f"/api/v1/history/{a['id']}").status_code == 404


def test_positions_shared_and_cleaned_up():
    fen = "4k3/8/8/8/8/8/4P3/4K3 w - - 0 1"
    a, b = create(fen=fen), create(fen=fen)
    assert count(PositionRow, fen=fen) == 1
    client.delete(f"/api/v1/history/{a['id']}")
    assert count(PositionRow, fen=fen) == 1  # still used by b
    client.delete(f"/api/v1/history/{b['id']}")
    assert count(PositionRow, fen=fen) == 0


def test_engine_config_defaults_apply():
    original = client.get("/api/v1/engine/config").json()["defaults"]
    try:
        r = client.put("/api/v1/engine/config", json={"depth": 1, "time_limit": 2, "candidates": 1})
        assert r.json()["defaults"] == {"depth": 1, "time_limit": 2.0, "candidates": 1}
        a = client.post("/api/v1/analysis", json={"fen": FORK}).json()
        assert (a["depth"], a["time_limit"], a["candidates"]) == (1, 2.0, 1)
        assert client.put("/api/v1/engine/config", json={"depth": 0}).status_code == 422
    finally:
        client.put("/api/v1/engine/config", json=original)


def test_play_move():
    r = client.post("/api/v1/positions/move", json={"fen": START, "move": "e2e4"}).json()
    assert r["san"] == "e4" and r["fen"].startswith("rnbqkbnr/pppppppp/8/8/4P3/") and len(r["legal_moves"]) == 20
    assert client.post("/api/v1/positions/move", json={"fen": START, "move": "e2e5"}).status_code == 422
    assert client.post("/api/v1/positions/move", json={"fen": START, "move": "zz"}).status_code == 422


def test_not_found_and_not_ready():
    missing = uuid.uuid4()
    assert client.get(f"/api/v1/analysis/{missing}").status_code == 404
    assert client.get(f"/api/v1/analysis/{missing}/variations").status_code == 404
    with SessionLocal.begin() as db:
        row = AnalysisRow(position=PositionRow(fen=START), engine_version="x", search_depth=1, candidates=1,
                          config={}, analysis_status="pending")
        db.add(row)
        db.flush()
        rid = row.id
    assert client.get(f"/api/v1/analysis/{rid}/variations").status_code == 409
    assert client.post(f"/api/v1/analysis/{rid}/explain", json={}).status_code == 409
    # A fresh job may belong to another live backend process: startup cleanup must leave it alone.
    service.fail_stale_jobs()
    assert client.get(f"/api/v1/analysis/{rid}").json()["status"] == "pending"
    # Once it is older than any real analysis can take, it is failed (here: when a client polls it).
    with SessionLocal.begin() as db:
        db.get(AnalysisRow, rid).created_at = datetime.now(UTC) - service.STALE_AFTER - timedelta(seconds=1)
    after = client.get(f"/api/v1/analysis/{rid}").json()
    assert after["status"] == "failed" and "interrupted" in after["error"]


def test_engine_failure_becomes_failed_job(monkeypatch):
    def boom(*_a):
        raise RuntimeError("engine exploded")
    monkeypatch.setattr(service, "run_analysis", boom)
    r = client.post("/api/v1/analysis", json={"fen": FORK, "depth": 1})
    assert r.status_code == 201 and r.json()["status"] == "failed" and "engine exploded" in r.json()["error"]


def test_async_worker_pool(monkeypatch):
    """Real process pool: POST returns before the search finishes; polling sees it complete."""
    monkeypatch.setattr(settings, "analysis_workers", 1)
    service.start_workers()
    try:
        r = client.post("/api/v1/analysis", json={"fen": FORK, "depth": 3})
        assert r.status_code == 202 and r.json()["status"] == "running"
        deadline = time.time() + 60
        while (s := client.get(f"/api/v1/analysis/{r.json()['id']}").json())["status"] == "running":
            assert time.time() < deadline, "job did not finish"
            time.sleep(0.2)
        assert s["status"] == "done" and s["best_move"] == "d5c7"
    finally:
        service.stop_workers()


def test_health_reports_database():
    assert client.get("/health").json()["database"] == "ok"
    assert main.engine_status()["database"] == "ok"


@pytest.mark.parametrize("limit", [0, 1000])
def test_history_limit_is_clamped(limit):
    assert client.get(f"/api/v1/history?limit={limit}").status_code == 200


def test_queue_limit_returns_429(monkeypatch):
    monkeypatch.setattr(settings, "max_queued_jobs", 0)
    r = client.post("/api/v1/analysis", json={"fen": FORK, "depth": 1})
    assert r.status_code == 429 and r.headers["retry-after"] == "5"


def test_metrics_and_request_id():
    r = client.get("/health", headers={"X-Request-ID": "abc123"})
    assert r.headers["x-request-id"] == "abc123"
    m = client.get("/metrics").text
    assert 'http_requests_total{method="GET",route="/health",status="200"}' in m
    assert "database_up 1" in m and "analysis_jobs{" in m
    client.get(f"/api/v1/analysis/{uuid.uuid4()}")
    assert 'route="/api/v1/analysis/{analysis_id}",status="404"' in client.get("/metrics").text  # templated route


def test_clear_all_history():
    create(name="one")
    create(fen=START, name="two")
    r = client.delete("/api/v1/history")
    assert r.status_code == 200 and r.json()["deleted"] >= 2
    assert client.get("/api/v1/history").json() == {"total": 0, "items": []}
    assert count(PositionRow) == 0 and count(AnalysisFeatureRow) == 0 and count(ExplanationRow) == 0
    assert client.delete("/api/v1/history").json()["deleted"] == 0  # idempotent


def test_progress_visible_while_running_then_hidden():
    with SessionLocal.begin() as db:
        row = AnalysisRow(position=PositionRow(fen=FORK), engine_version="x", search_depth=3, candidates=2,
                          config={}, analysis_status="running")
        db.add(row)
        db.flush()
        rid = row.id
    payload = service.run_analysis(FORK, 3, None, 2, rid)  # reports after each depth
    running = client.get(f"/api/v1/analysis/{rid}").json()
    p = running["progress"]
    assert running["status"] == "running" and p["depth"] == 3
    assert p["candidates"][0]["san"] == "Nc7+" and p["candidates"][0]["pv_san"][0] == "Nc7+"
    assert p["candidates"][0]["score_white"] > 0  # White to move and winning
    service.store_result(rid, payload)
    done = client.get(f"/api/v1/analysis/{rid}").json()
    assert done["status"] == "done" and done["progress"] is None and done["best_move"] == "d5c7"
