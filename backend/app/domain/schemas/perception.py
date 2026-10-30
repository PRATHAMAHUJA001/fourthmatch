"""PerceptionResult contract. Every numeric field is computed in Python from SAM.

ORM persistence lives in infra/db/models/perception.py (perception_results).
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.enums import DamageSource, EvidenceQuality


class PerceptionResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    delivery_id: int
    sam_run_id: int
    category: str
    prompt: str
    track_count: int = Field(ge=0)  # Python: distinct SAM object_ids
    max_visible: int = Field(ge=0)  # Python: max distinct ids in any single frame
    evidence_quality: EvidenceQuality
    reasons: list[str] = Field(default_factory=list)  # stable codes, e.g. low_frame_coverage

    @model_validator(mode="after")
    def _check_counts(self) -> PerceptionResult:
        if self.max_visible > self.track_count:
            raise ValueError("max_visible cannot exceed track_count")
        if self.track_count == 0 and self.evidence_quality is not EvidenceQuality.NONE:
            raise ValueError("zero tracks must yield evidence_quality=none")
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
