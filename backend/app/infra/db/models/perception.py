"""Perception ORM: sam_runs (provenance), tracks, damage_flags, perception_results.

Counts come only from SAM tracks. sam_runs and tracks are separate tables on purpose.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infra.db.session import Base

if TYPE_CHECKING:
    from app.infra.db.models.purchasing import Delivery


def _utcnow() -> datetime:
    return datetime.now(UTC)


class SamRun(Base):
    __tablename__ = "sam_runs"
    __table_args__ = (
        UniqueConstraint("video_sha256", "prompt", "seg_model", "proxy_fps", name="uq_sam_runs_cache_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    delivery_id: Mapped[int] = mapped_column(ForeignKey("deliveries.id"), index=True)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id"), nullable=True, index=True)
    video_sha256: Mapped[str] = mapped_column(String(64), index=True)
    video_file_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    seg_model: Mapped[str] = mapped_column(String(80))  # copied from ModelConfig at run time
    prompt: Mapped[str] = mapped_column(String(80))
    category: Mapped[str] = mapped_column(String(32))
    proxy_fps: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    raw_cache_path: Mapped[str | None] = mapped_column(String(300), nullable=True)
    distinct_track_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    delivery: Mapped[Delivery] = relationship(back_populates="sam_runs")
    tracks: Mapped[list[Track]] = relationship(back_populates="sam_run", cascade="all, delete-orphan")


class Track(Base):
    """One SAM 3.1 track (unique object_id per sam_run). Only the pipeline writes these."""

    __tablename__ = "tracks"
    __table_args__ = (UniqueConstraint("sam_run_id", "object_id", name="uq_tracks_run_object"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    delivery_id: Mapped[int] = mapped_column(ForeignKey("deliveries.id"), index=True)
    sam_run_id: Mapped[int] = mapped_column(ForeignKey("sam_runs.id"), index=True)
    object_id: Mapped[str] = mapped_column(String(64))
    prompt: Mapped[str] = mapped_column(String(80))
    category: Mapped[str] = mapped_column(String(32))
    first_frame: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_frame: Mapped[int | None] = mapped_column(Integer, nullable=True)
    frame_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    delivery: Mapped[Delivery] = relationship(back_populates="tracks")
    sam_run: Mapped[SamRun] = relationship(back_populates="tracks")
    damage_flags: Mapped[list[DamageFlag]] = relationship(back_populates="track", cascade="all, delete-orphan")


class DamageFlag(Base):
    __tablename__ = "damage_flags"

    id: Mapped[int] = mapped_column(primary_key=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id"), index=True)
    delivery_id: Mapped[int] = mapped_column(ForeignKey("deliveries.id"), index=True)
    frame_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason_code: Mapped[str] = mapped_column(String(80))
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="sam")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    track: Mapped[Track] = relationship(back_populates="damage_flags")


class PerceptionResult(Base):
    """Persisted PerceptionResult. Numeric fields are Python-computed from SAM."""

    __tablename__ = "perception_results"
    __table_args__ = (UniqueConstraint("sam_run_id", "category", name="uq_perception_run_category"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    delivery_id: Mapped[int] = mapped_column(ForeignKey("deliveries.id"), index=True)
    sam_run_id: Mapped[int] = mapped_column(ForeignKey("sam_runs.id"), index=True)
    category: Mapped[str] = mapped_column(String(32))
    prompt: Mapped[str] = mapped_column(String(80))
    track_count: Mapped[int] = mapped_column(Integer)
    max_visible: Mapped[int] = mapped_column(Integer)
    evidence_quality: Mapped[str] = mapped_column(String(16))  # strong|weak|none
    reasons: Mapped[list[Any]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

