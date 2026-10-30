"""SAM run / track contracts. ORM lives in infra/db/models/perception.py."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import SamRunStatus


class SamRunCreate(BaseModel):
    delivery_id: int
    job_id: str | None = None
    video_sha256: str = Field(min_length=64, max_length=64)
    video_file_id: str | None = None
    seg_model: str = Field(min_length=1)  # copied from ModelConfig at run time
    prompt: str = Field(min_length=1)
    category: str = Field(min_length=1)
    proxy_fps: float | None = None


class SamRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    delivery_id: int
    job_id: str | None = None
    video_sha256: str
    video_file_id: str | None = None
    seg_model: str
    prompt: str
    category: str
    proxy_fps: float | None = None
    status: SamRunStatus
    raw_cache_path: str | None = None
    distinct_track_count: int | None = None
    error: str | None = None
    created_at: datetime
    finished_at: datetime | None = None


class SamTrackRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    delivery_id: int
    sam_run_id: int
    object_id: str
    prompt: str
    category: str
    first_frame: int | None = None
    last_frame: int | None = None
    frame_count: int | None = None
    confidence: float | None = None
