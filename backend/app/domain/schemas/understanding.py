"""Stage B (understanding) contract: noun phrases + scene facts. Never counts."""
from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class CameraMotion(StrEnum):
    STATIC = "static"
    PAN = "pan"
    HANDHELD = "handheld"


class Occlusion(StrEnum):
    NONE = "none"
    PARTIAL = "partial"
    HEAVY = "heavy"


class Lighting(StrEnum):
    GOOD = "good"
    POOR = "poor"


class UnderstandingLine(BaseModel):
    po_line_id: str
    noun_phrase: str = Field(min_length=1)
    distinguishing_feature: str | None = None


class SceneFacts(BaseModel):
    camera_motion: CameraMotion
    occlusion: Occlusion
    lighting: Lighting
    unlisted_objects: list[str] = Field(default_factory=list)


class Understanding(BaseModel):
    lines: list[UnderstandingLine] = Field(default_factory=list)
    scene: SceneFacts


class FootageNeeded(BaseModel):
    """Stage C follow-up: one sentence, insufficient lines only."""

    footage_needed: str = Field(min_length=1)
