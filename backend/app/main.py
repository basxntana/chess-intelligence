import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from . import observability, service
from .chess_core import Position, validate_fen
from .chess_core.notation import san
from .config import settings
from .db import SessionLocal, db_ok
from .explanation import explain_move
from .intelligence import candidate_entry, score_move
from .models import AnalysisRow, PositionRow
from .search import SearchConfig

UCI = r"^[a-h][1-8][a-h][1-8][qrbn]?$"
LANGUAGE = r"^[A-Za-z][A-Za-z ()-]*$"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if db_ok():
        service.fail_stale_jobs()
    service.start_workers()
    yield
    service.stop_workers()


if settings.json_logs:
    observability.configure_logging(settings.log_level)
app = FastAPI(title="Chess Intelligence API", version=settings.engine_version, lifespan=lifespan)
observability.install(app)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])
api = APIRouter(prefix="/api/v1")


def get_db():
    with SessionLocal() as db:
        yield db


DB = Annotated[Session, Depends(get_db)]


class FenIn(BaseModel):
    fen: str = Field(min_length=1, max_length=100)  # longest legal FEN is ~90 chars


# ---------- engine config (defaults for new analyses) ----------
class EngineConfigIn(BaseModel):
    depth: int = Field(4, ge=1, le=12)
    time_limit: float | None = Field(5.0, gt=0, le=60)  # seconds; bounds keep one job from hogging a worker
    candidates: int = Field(3, ge=1, le=5)


# shortcut: defaults live in process memory (reset on restart, per API process); move to a table if several
# API processes must share them.
ENGINE_DEFAULTS = EngineConfigIn()


@api.get("/engine/status")
def engine_status():
    return {"engine_version": settings.engine_version, "chess_core": "ready", "search": "ready",
            "workers": settings.analysis_workers, "database": "ok" if db_ok() else "unavailable"}


@api.get("/engine/config")
def engine_config():
    return {"engine_version": settings.engine_version, "defaults": ENGINE_DEFAULTS.model_dump(),
            "search": asdict(SearchConfig(**ENGINE_DEFAULTS.model_dump()))}


@api.put("/engine/config")
def update_engine_config(body: EngineConfigIn):
    global ENGINE_DEFAULTS
    ENGINE_DEFAULTS = body
    return engine_config()


# ---------- positions ----------
@app.get("/health")
def health():
    return {"status": "ok", "database": "ok" if db_ok() else "unavailable"}


@api.post("/positions/validate")
def validate_position(body: FenIn):
    return validate_fen(body.fen.strip())


@api.post("/positions/fen")
def normalize_fen(body: FenIn):
    """Parse and re-serialize a FEN (also fills omitted move counters)."""
    r = validate_fen(body.fen.strip())
    return {"fen": r.get("fen"), "syntax_valid": r["syntax_valid"], "legal": r["legal"], "errors": r["errors"]}


class MoveIn(FenIn):
    move: str = Field(pattern=UCI)


@api.post("/positions/move")
def play_move(body: MoveIn):
    """Apply a legal move (the board UI has no chess rules of its own) and return the new position's validation."""
    r = _legal_or_422(body.fen)
    if body.move not in r["legal_moves"]:
        raise HTTPException(status_code=422, detail=[f"illegal move: {body.move}"])
    pos = Position(r["fen"])
    m = pos.parse_uci(body.move)
    move_san = san(pos, m)
    pos.make(m)
    return {"move": body.move, "san": move_san, **validate_fen(pos.fen())}


def _legal_or_422(fen: str) -> dict:
    r = validate_fen(fen.strip())
    if not r["legal"]:
        raise HTTPException(status_code=422, detail=r["errors"])
    return r


# ---------- analysis ----------
class AnalysisIn(FenIn):
    depth: int | None = Field(None, ge=1, le=12)  # unset fields take the engine config defaults
    time_limit: float | None = Field(None, gt=0, le=60)
    candidates: int | None = Field(None, ge=1, le=5)
    name: str | None = Field(None, max_length=120)


def _iso(t: datetime | None) -> str | None:
    return t.isoformat() if t else None


def _view(row: AnalysisRow, full: bool = True) -> dict:
    out = {"id": str(row.id), "name": row.name, "fen": row.position.fen, "status": row.analysis_status,
           "error": row.error, "engine_version": row.engine_version, "depth": row.search_depth,
           "time_limit": row.time_limit, "candidates": row.candidates, "best_move": row.best_move,
           "evaluation_score": row.evaluation_score, "mate_in": row.mate_in, "created_at": _iso(row.created_at),
           "started_at": _iso(row.started_at), "completed_at": _iso(row.completed_at)}
    if full:
        out["config"] = row.config
        out["progress"] = row.progress if row.analysis_status == "running" else None
        out["result"] = row.result
    return out


def _get(db: Session, analysis_id: uuid.UUID) -> AnalysisRow:
    row = db.get(AnalysisRow, analysis_id)
    if row is None:
        raise HTTPException(status_code=404, detail="analysis not found")
    return row


@api.post("/analysis", status_code=202)
def create_analysis(body: AnalysisIn, response: Response, db: DB):
    """Queue an analysis with the custom engine. Poll GET /analysis/{id} until status is done or failed."""
    r = _legal_or_422(body.fen)
    queued = db.scalar(select(func.count()).select_from(AnalysisRow)
                       .where(AnalysisRow.analysis_status.in_(("pending", "running"))))
    if queued >= settings.max_queued_jobs:
        raise HTTPException(status_code=429, detail="analysis queue is full, try again shortly",
                            headers={"Retry-After": "5"})
    d = ENGINE_DEFAULTS
    depth = body.depth or d.depth
    time_limit = body.time_limit if body.time_limit is not None else d.time_limit
    candidates = body.candidates or d.candidates
    cfg = SearchConfig(depth=depth, time_limit=time_limit, candidates=candidates)
    position = db.scalar(select(PositionRow).where(PositionRow.fen == r["fen"]).limit(1)) or PositionRow(fen=r["fen"])
    row = AnalysisRow(position=position, name=body.name, engine_version=settings.engine_version, search_depth=depth,
                      time_limit=time_limit, candidates=candidates, config=asdict(cfg), analysis_status="pending")
    db.add(row)
    db.commit()
    service.submit(row.id, r["fen"], depth, time_limit, candidates)
    db.refresh(row)
    if row.analysis_status in ("done", "failed"):
        response.status_code = 201  # finished inline (no worker pool)
    return _view(row)


@api.get("/analysis/{analysis_id}")
def get_analysis(analysis_id: uuid.UUID, db: DB):
    row = _get(db, analysis_id)
    if row.analysis_status in ("pending", "running") and service.fail_stale_jobs(analysis_id):
        db.refresh(row)  # a poller must not wait forever on a job whose server died
    return _view(row)


def _done(db: Session, analysis_id: uuid.UUID) -> AnalysisRow:
    row = _get(db, analysis_id)
    if row.analysis_status != "done":
        raise HTTPException(status_code=409, detail=f"analysis is {row.analysis_status}")
    return row


@api.get("/analysis/{analysis_id}/variations")
def get_variations(analysis_id: uuid.UUID, db: DB):
    row = _done(db, analysis_id)
    return {"id": str(row.id), "fen": row.position.fen, "variations": row.result["variations"]}


class ExplainIn(BaseModel):
    move: str | None = Field(None, pattern=UCI)  # default: the engine's best move
    use_llm: bool = False  # rule-based is always available; the LLM is opt-in (cost, latency)
    language: str = Field("English", min_length=2, max_length=30, pattern=LANGUAGE)


@api.post("/analysis/{analysis_id}/explain")
def explain_analysis(analysis_id: uuid.UUID, body: ExplainIn, db: DB):
    row = _done(db, analysis_id)
    insights = row.result["insights"]
    if not insights["candidates"]:
        raise HTTPException(status_code=409, detail="no moves to explain in a finished game")
    pos = Position(row.position.fen)
    if body.move and all(c["move"] != body.move for c in insights["candidates"]):
        if body.move not in {m.uci for m in pos.legal_moves()}:
            raise HTTPException(status_code=422, detail=[f"illegal move: {body.move}"])
        cfg = SearchConfig(depth=row.search_depth, time_limit=row.time_limit, candidates=row.candidates)
        scored = score_move(pos, pos.parse_uci(body.move), row.search_depth, cfg)
        insights = {**insights, "candidates": [*insights["candidates"], candidate_entry(pos, scored, row.search_depth)]}
    explanation = explain_move(pos, insights, body.move, use_llm=body.use_llm, language=body.language)
    row.explanations.append(service.explanation_row(explanation))
    db.commit()
    return explanation


# ---------- history ----------
@api.get("/history")
def list_history(db: DB, limit: int = 50, offset: int = 0):
    limit = max(1, min(limit, 200))
    rows = db.scalars(select(AnalysisRow).order_by(AnalysisRow.created_at.desc()).limit(limit).offset(max(offset, 0)))
    total = db.scalar(select(func.count()).select_from(AnalysisRow))
    return {"total": total, "items": [_view(r, full=False) for r in rows]}


@api.delete("/history")
def clear_history(db: DB):
    """Delete every analysis (features/explanations go by cascade) and the positions they used."""
    deleted = db.scalar(select(func.count()).select_from(AnalysisRow))
    db.execute(delete(AnalysisRow))
    db.execute(delete(PositionRow))
    db.commit()
    return {"deleted": deleted}


@api.get("/history/{analysis_id}")
def get_history(analysis_id: uuid.UUID, db: DB):
    return _view(_get(db, analysis_id))


class RenameIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


@api.patch("/history/{analysis_id}")
def rename_history(analysis_id: uuid.UUID, body: RenameIn, db: DB):
    row = _get(db, analysis_id)
    row.name = body.name.strip()
    db.commit()
    return _view(row, full=False)


@api.delete("/history/{analysis_id}", status_code=204)
def delete_history(analysis_id: uuid.UUID, db: DB):
    row = _get(db, analysis_id)
    position = row.position
    db.delete(row)
    db.flush()
    db.refresh(position)
    if not position.analyses:  # no other analysis uses this position: remove it too
        db.delete(position)
    db.commit()
    return Response(status_code=204)


app.include_router(api)
