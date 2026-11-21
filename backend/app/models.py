"""Persistence (TRD 7). Engine version + search config are stored with every analysis for reproducibility.
The TRD `users` table is omitted: the MVP has no accounts (PRD excludes account integrations)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

Json = JSON().with_variant(JSONB(), "postgresql")
STATUSES = ("pending", "running", "done", "failed")


class PositionRow(Base):
    __tablename__ = "positions"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    fen: Mapped[str] = mapped_column(String(100), index=True)
    name: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    analyses: Mapped[list[AnalysisRow]] = relationship(back_populates="position", cascade="all, delete-orphan")


class AnalysisRow(Base):
    __tablename__ = "analyses"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    position_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("positions.id", ondelete="CASCADE"), index=True)
    name: Mapped[str | None] = mapped_column(String(120))
    engine_version: Mapped[str] = mapped_column(String(20))
    search_depth: Mapped[int] = mapped_column(Integer)
    time_limit: Mapped[float | None] = mapped_column(Float)
    candidates: Mapped[int] = mapped_column(Integer)
    config: Mapped[dict] = mapped_column(Json)  # full SearchConfig incl. evaluation weights
    analysis_status: Mapped[str] = mapped_column(String(16), index=True, default="pending")
    evaluation_score: Mapped[int | None] = mapped_column(Integer)  # centipawns, White's perspective
    mate_in: Mapped[int | None] = mapped_column(Integer)
    best_move: Mapped[str | None] = mapped_column(String(5))
    principal_variation: Mapped[list | None] = mapped_column(Json)
    result: Mapped[dict | None] = mapped_column(Json)  # search + evaluation + insights + variations
    progress: Mapped[dict | None] = mapped_column(Json)  # best-so-far while running (one update per search depth)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    position: Mapped[PositionRow] = relationship(back_populates="analyses")
    features: Mapped[list[AnalysisFeatureRow]] = relationship(cascade="all, delete-orphan", passive_deletes=True)
    explanations: Mapped[list[ExplanationRow]] = relationship(cascade="all, delete-orphan", passive_deletes=True)


class AnalysisFeatureRow(Base):
    __tablename__ = "analysis_features"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(16))  # tactical | strategic
    feature_type: Mapped[str] = mapped_column(String(40), index=True)
    side: Mapped[str | None] = mapped_column(String(8))
    description: Mapped[str | None] = mapped_column(Text)
    squares: Mapped[list] = mapped_column(Json, default=list)
    evidence: Mapped[dict] = mapped_column(Json, default=dict)
    severity: Mapped[int | None] = mapped_column(Integer)


class ExplanationRow(Base):
    __tablename__ = "explanations"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    analysis_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"), index=True)
    move: Mapped[str] = mapped_column(String(5))
    explanation_type: Mapped[str] = mapped_column(String(16))  # rule_based | llm
    language: Mapped[str] = mapped_column(String(30))
    explanation_content: Mapped[dict] = mapped_column(Json)
    model_version: Mapped[str | None] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
