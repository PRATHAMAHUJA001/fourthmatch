"""Typed model configuration. No literal model IDs live here."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ModelConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    model_api_key: str = Field(min_length=1)
    meta_base_url: str = Field(min_length=1)
    perception_model: str = Field(min_length=1)
    decision_model: str = Field(min_length=1)
    compiler_model: str = Field(min_length=1)
    bulk_model: str = Field(min_length=1)
    wonder_model: str | None = None
    seg_model: str = Field(min_length=1)
    image_model: str = Field(min_length=1)
    voice_model: str = Field(min_length=1)


class CountingConfig(BaseModel):
    """Counting thresholds. Durations in seconds; converted via proxy_fps."""

    model_config = ConfigDict(frozen=True)

    sam_score_min: float = 0.5
    min_track_seconds: float = 1.0
    merge_max_gap_seconds: float = 3.0
    merge_min_iou: float = 0.3
    max_short_track_ratio: float = 0.34
    max_merge_ratio: float = 0.34  # merges / observed_count
    proxy_fps: float = 2.0

    @property
    def min_track_frames(self) -> int:
        return max(1, round(self.min_track_seconds * self.proxy_fps))

    @property
    def merge_max_gap_frames(self) -> int:
        return max(0, round(self.merge_max_gap_seconds * self.proxy_fps))
