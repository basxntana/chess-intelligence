"""Structured JSON logging, request IDs, and Prometheus-format metrics (no extra dependencies)."""
from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from collections import defaultdict
from threading import Lock

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select

log = logging.getLogger("chess_intelligence")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = {"ts": round(record.created, 3), "level": record.levelname.lower(), "logger": record.name,
               "msg": record.getMessage(), **getattr(record, "fields", {})}
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).handlers[:] = []
        logging.getLogger(name).propagate = name != "uvicorn.access"  # our middleware logs each request


_lock = Lock()
_requests: dict[tuple[str, str, int], int] = defaultdict(int)
_durations: dict[tuple[str, str], list[float]] = defaultdict(lambda: [0.0, 0])  # sum, count


def install(app: FastAPI) -> None:
    @app.middleware("http")
    async def access_log(request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = rid
            return response
        except Exception:
            log.exception("unhandled error", extra={"fields": {"request_id": rid, "path": request.url.path}})
            raise
        finally:
            elapsed = time.perf_counter() - start
            route = getattr(request.scope.get("route"), "path", "unmatched")  # template, not the raw id
            with _lock:
                _requests[(request.method, route, status)] += 1
                d = _durations[(request.method, route)]
                d[0] += elapsed
                d[1] += 1
            if route != "/metrics":
                log.info("request", extra={"fields": {"request_id": rid, "method": request.method, "route": route,
                                                      "status": status, "duration_ms": round(elapsed * 1000, 1)}})

    @app.get("/metrics", include_in_schema=False)
    def metrics() -> PlainTextResponse:
        from .db import SessionLocal, db_ok
        from .models import AnalysisRow

        lines = ["# TYPE http_requests_total counter"]
        with _lock:
            for (method, route, status), n in sorted(_requests.items()):
                lines.append(f'http_requests_total{{method="{method}",route="{route}",status="{status}"}} {n}')
            lines.append("# TYPE http_request_duration_seconds summary")
            for (method, route), (total, n) in sorted(_durations.items()):
                labels = f'method="{method}",route="{route}"'
                lines.append(f"http_request_duration_seconds_sum{{{labels}}} {total:.6f}")
                lines.append(f"http_request_duration_seconds_count{{{labels}}} {n}")
        up = db_ok()
        lines += ["# TYPE database_up gauge", f"database_up {int(up)}"]
        if up:
            with SessionLocal() as db:
                rows = db.execute(select(AnalysisRow.analysis_status, func.count()).group_by(AnalysisRow.analysis_status))
                lines.append("# TYPE analysis_jobs gauge")
                lines += [f'analysis_jobs{{status="{s}"}} {n}' for s, n in rows]
        return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")
