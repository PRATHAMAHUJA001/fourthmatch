"""Perception contracts. Every numeric field is computed in Python from SAM.

ORM persistence lives in infra/db/models/perception.py (perception_results).
Domain Track/TrackFrame carry per-frame SAM detail; the DB `tracks` row is
the aggregate of one Track, the per-frame detail lives in the SAM cache.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.enums import DamageSource, EvidenceQuality


class BBox(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float


class TrackFrame(BaseModel):
    frame_index: int
    bbox: BBox
    mask_ref: str | None = None
    score: float | None = None


class Track(BaseModel):
    """One SAM track: same object_id on every frame it appears in."""

    track_id: str
    phrase: str
    frames: list[TrackFrame] = Field(default_factory=list)

    @property
    def first_frame(self) -> int | None:
        return self.frames[0].frame_index if self.frames else None

    @property
    def last_frame(self) -> int | None:
        return self.frames[-1].frame_index if self.frames else None

    @property
    def mean_score(self) -> float | None:
        scores = [f.score for f in self.frames if f.score is not None]
        return sum(scores) / len(scores) if scores else None


class MergeRecord(BaseModel):
    merged_track_ids: list[str]  # [earlier, later] SAM object_ids joined
    into_track_id: str
    gap_frames: int
    boundary_iou: float


class CountResult(BaseModel):
    observed_count: int = Field(ge=0)
    max_visible: int = Field(ge=0)
    per_frame_counts: list[int] = Field(default_factory=list)
    kept_track_ids: list[str] = Field(default_factory=list)
    merged_tracks: list[Track] = Field(default_factory=list)  # in-memory only, for Stages D/E
    merges: list[MergeRecord] = Field(default_factory=list)
    evidence_quality: EvidenceQuality
    reasons: list[str] = Field(default_factory=list)


class PerceptionResult(BaseModel):
    """One PO line's persisted outcome. All numbers computed in Python."""

    model_config = ConfigDict(from_attributes=True)

    delivery_id: int
    po_line_id: int | None = None
    sam_run_id: int
    category: str
    noun_phrase: str
    observed_count: int = Field(ge=0)  # Python: merged SAM tracks
    max_visible: int = Field(ge=0)  # Python: max objects in any single frame
    per_frame_counts: list[int] = Field(default_factory=list)
    damaged_track_ids: list[str] = Field(default_factory=list)
    evidence_quality: EvidenceQuality
    reasons: list[str] = Field(default_factory=list)  # stable codes, e.g. no_tracks
    footage_needed: str | None = None  # model sentence, insufficient lines only

    @model_validator(mode="after")
    def _check_counts(self) -> PerceptionResult:
        if self.max_visible > self.observed_count:
            raise ValueError("max_visible cannot exceed observed_count")
        if self.observed_count == 0 and "no_tracks" not in self.reasons:
            raise ValueError("zero tracks must carry reason code no_tracks")
        if self.evidence_quality is EvidenceQuality.RELIABLE and self.footage_needed is not None:
            raise ValueError("reliable lines never carry footage_needed")
        return self


class PerceptionResultRead(PerceptionResult):
    id: int
    created_at: datetime


class DamageFlagCreate(BaseModel):
    track_id: int
    delivery_id: int
    frame_index: int | None = None
    reason_code: str
    confidence: float | None = None
    source: DamageSource = DamageSource.SAM


class DamageFlagRead(DamageFlagCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
