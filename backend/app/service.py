"""Analysis jobs: run_analysis() is pure (runs in a worker process); store_result() persists its output."""
from __future__ import annotations

import uuid
from concurrent.futures import Future, ProcessPoolExecutor
from dataclasses import asdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, update
from sqlalchemy.exc import SQLAlchemyError

from .chess_core import Position
from .chess_core.notation import line_san, san
from .config import settings
from .db import SessionLocal
from .evaluation import explain
from .explanation import explain_move
from .intelligence import analyze
from .models import AnalysisFeatureRow, AnalysisRow, ExplanationRow
from .search import SearchConfig, search


def run_analysis(fen: str, depth: int, time_limit: float | None, candidates: int,
                 analysis_id: uuid.UUID | None = None) -> dict:
    """Search + intelligence + rule-based explanation + variations. Runs in a worker process; its only I/O is the
    best-so-far progress row written after each search depth (when `analysis_id` is given)."""
    pos = Position(fen)
    cfg = SearchConfig(depth=depth, time_limit=time_limit, candidates=candidates)
    report = (lambda d, cands, nodes, secs: report_progress(analysis_id, pos, d, cands, nodes, secs)) \
        if analysis_id else None
    result = search(pos, cfg, on_iteration=report)
    insights = analyze(pos, cfg, result=result)
    del insights["search"]
    explanation = explain_move(pos, insights) if insights["candidates"] else None
    return {"search": asdict(result), "evaluation": explain(pos), "insights": insights,
            "variations": variations(pos, insights["candidates"]), "explanation": explanation}


def report_progress(analysis_id: uuid.UUID, pos: Position, depth: int, cands: list, nodes: int, secs: float) -> None:
    """Best move so far, in a form the UI can show immediately (SAN, White-perspective score)."""
    sign = 1 if pos.turn == "w" else -1
    progress = {"depth": depth, "nodes": nodes, "seconds": round(secs, 2),
                "candidates": [{"move": c.move, "san": san(pos, pos.parse_uci(c.move)), "score_white": c.score * sign,
                                "mate_in": c.mate_in, "pv_san": line_san(pos, c.pv)} for c in cands]}
    try:
        with SessionLocal.begin() as db:
            db.execute(update(AnalysisRow).where(AnalysisRow.id == analysis_id, AnalysisRow.analysis_status == "running")
                       .values(progress=progress))
    except SQLAlchemyError:
        pass  # progress is a nicety; never let it fail the analysis


def variations(pos: Position, candidates: list[dict]) -> list[dict]:
    """Each candidate's principal variation as plies with SAN and the FEN after the move (for the move explorer)."""
    out = []
    for c in candidates:
        plies = []
        for i, uci in enumerate(c["pv"]):
            m = pos.parse_uci(uci)
            plies.append({"ply": i + 1, "uci": uci, "san": san(pos, m)})
            pos.make(m)
            plies[-1]["fen"] = pos.fen()
        for _ in plies:
            pos.unmake()
        out.append({"move": c["move"], "score": c["score"], "mate_in": c["mate_in"], "plies": plies})
    return out


def store_result(analysis_id: uuid.UUID, payload: dict | None, error: str | None = None) -> None:
    with SessionLocal.begin() as db:
        row = db.get(AnalysisRow, analysis_id)
        if row is None:  # deleted while running
            return
        row.completed_at = datetime.now(UTC)
        if error is not None:
            row.analysis_status, row.error = "failed", error[:2000]
            return
        s = payload["search"]
        row.analysis_status, row.result = "done", payload
        row.best_move, row.principal_variation = s["best_move"], s["pv"]
        row.evaluation_score, row.mate_in = s["score_white"], s["mate_in"]
        insights = payload["insights"]
        for f in insights["position"]["tactics"]:
            row.features.append(AnalysisFeatureRow(
                category="tactical", feature_type=f["motif"], side=f["by"], squares=f["squares"],
                evidence=f["evidence"], severity=f["severity"], description=f"{f['motif']} by {f['by']}"))
        for f in insights["position"]["strategic"]:
            row.features.append(AnalysisFeatureRow(
                category="strategic", feature_type=f["feature"], side=f["side"], squares=f["squares"],
                evidence=f["evidence"], severity=f["score"], description=f["category"]))
        if payload["explanation"]:
            row.explanations.append(explanation_row(payload["explanation"]))


def explanation_row(e: dict) -> ExplanationRow:
    return ExplanationRow(move=e["move"], explanation_type=e["source"], language=e["language"],
                          explanation_content=e, model_version=e["model"] or f"rules@{settings.engine_version}")


# ---------- job runner ----------
_executor: ProcessPoolExecutor | None = None


def start_workers() -> None:
    global _executor
    if settings.analysis_workers > 0 and _executor is None:
        _executor = ProcessPoolExecutor(max_workers=settings.analysis_workers)


def stop_workers() -> None:
    global _executor
    if _executor is not None:
        _executor.shutdown(wait=False, cancel_futures=True)
        _executor = None


STALE_AFTER = timedelta(minutes=10)  # far beyond the 60 s time limit; only a dead server leaves a job this old


def fail_stale_jobs(analysis_id: uuid.UUID | None = None) -> int:
    """Mark jobs failed that no live process can still finish. Only jobs older than STALE_AFTER: another backend
    process (or one that started, failed to bind its port and exited) must not fail jobs that are really running."""
    cutoff = datetime.now(UTC) - STALE_AFTER
    q = (update(AnalysisRow)
         .where(AnalysisRow.analysis_status.in_(("pending", "running")),
                func.coalesce(AnalysisRow.started_at, AnalysisRow.created_at) < cutoff)
         .values(analysis_status="failed", error="interrupted (server stopped or job timed out)",
                 completed_at=datetime.now(UTC)))
    if analysis_id is not None:
        q = q.where(AnalysisRow.id == analysis_id)
    with SessionLocal.begin() as db:
        return db.execute(q).rowcount


def submit(analysis_id: uuid.UUID, fen: str, depth: int, time_limit: float | None, candidates: int) -> None:
    with SessionLocal.begin() as db:
        db.execute(update(AnalysisRow).where(AnalysisRow.id == analysis_id)
                   .values(analysis_status="running", started_at=datetime.now(UTC)))
    if _executor is None:  # ANALYSIS_WORKERS=0: run inline (tests, single-process dev)
        try:
            store_result(analysis_id, run_analysis(fen, depth, time_limit, candidates, analysis_id))
        except Exception as e:  # noqa: BLE001  any engine failure becomes a failed job, never a crashed request
            store_result(analysis_id, None, f"{type(e).__name__}: {e}")
        return

    def done(fut: Future) -> None:
        exc = fut.exception()
        store_result(analysis_id, None if exc else fut.result(), f"{type(exc).__name__}: {exc}" if exc else None)

    _executor.submit(run_analysis, fen, depth, time_limit, candidates, analysis_id).add_done_callback(done)
