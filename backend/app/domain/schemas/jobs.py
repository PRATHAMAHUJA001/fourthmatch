"""Job / JobEvent contracts. ORM lives in infra/db/models/jobs.py."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import JobKind, JobStatus


class JobCreate(BaseModel):
    kind: JobKind
    delivery_id: int | None = None
    po_id: int | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str
    status: JobStatus
    delivery_id: int | None = None
    po_id: int | None = None
    progress_pct: int = 0
    current_step: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class DeliveryCreated(BaseModel):
    delivery_id: int
    job_id: str


class JobEventCreate(BaseModel):
    event_type: str
    message: str
    payload: dict[str, Any] = Field(default_factory=dict)


class JobEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: str
    seq: int
    event_type: str
    message: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
