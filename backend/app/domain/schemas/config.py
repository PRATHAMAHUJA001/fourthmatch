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
