"""Core configuration: every model ID, base URL and key comes from .env only.

No other module reads model IDs from the environment and no model ID literal
appears anywhere else in backend/app. Future Meta clients receive Settings /
ModelConfig by injection (see infra/meta/client.py).
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.domain.schemas.config import ModelConfig

REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = REPO_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE if ENV_FILE.exists() else None,
        extra="ignore",
        populate_by_name=True,
    )

    model_api_key: str = Field(default="", validation_alias=AliasChoices("MODEL_API_KEY", "model_api_key"))
    meta_base_url: str = Field(
        default="https://api.meta.ai/v1",
        validation_alias=AliasChoices("META_BASE_URL", "meta_base_url"),
    )
    perception_model: str = Field(default="", validation_alias=AliasChoices("PERCEPTION_MODEL", "perception_model"))
    decision_model: str = Field(default="", validation_alias=AliasChoices("DECISION_MODEL", "decision_model"))
    compiler_model: str = Field(default="", validation_alias=AliasChoices("COMPILER_MODEL", "compiler_model"))
    bulk_model: str = Field(default="", validation_alias=AliasChoices("BULK_MODEL", "bulk_model"))
    wonder_model: str = Field(default="", validation_alias=AliasChoices("WONDER_MODEL", "wonder_model"))
    seg_model: str = Field(default="", validation_alias=AliasChoices("SEG_MODEL", "seg_model"))
    image_model: str = Field(default="", validation_alias=AliasChoices("IMAGE_MODEL", "image_model"))
    voice_model: str = Field(default="", validation_alias=AliasChoices("VOICE_MODEL", "voice_model"))

    database_url: str | None = Field(default=None, validation_alias=AliasChoices("DATABASE_URL", "database_url"))
    # Perception/counting thresholds. Durations in SECONDS, converted with
    # sam_proxy_fps in domain/counting.py so an fps change never silently
    # changes behaviour. Starting values only -- the eval decides.
    sam_score_min: float = Field(default=0.5, validation_alias=AliasChoices("SAM_SCORE_MIN", "sam_score_min"))
    min_track_seconds: float = Field(default=1.0, validation_alias=AliasChoices("MIN_TRACK_SECONDS", "min_track_seconds"))
    merge_max_gap_seconds: float = Field(
        default=3.0, validation_alias=AliasChoices("MERGE_MAX_GAP_SECONDS", "merge_max_gap_seconds")
    )
    merge_min_iou: float = Field(default=0.3, validation_alias=AliasChoices("MERGE_MIN_IOU", "merge_min_iou"))
    max_short_track_ratio: float = Field(
        default=0.34, validation_alias=AliasChoices("MAX_SHORT_TRACK_RATIO", "max_short_track_ratio")
    )
    max_merge_ratio: float = Field(default=0.34, validation_alias=AliasChoices("MAX_MERGE_RATIO", "max_merge_ratio"))
    sam_proxy_fps: float = Field(default=2.0, validation_alias=AliasChoices("SAM_PROXY_FPS", "sam_proxy_fps"))
    # Stage C phrase-coverage check: category -> generic noun run alongside
    # the model's phrase. Keys are matched normalised (case/underscore/space).
    category_generic_nouns: dict[str, str] = Field(
        default={
            "cartons": "box",
            "bagged material": "sack",
            "steel coils": "steel coil",
        },
        validation_alias=AliasChoices("CATEGORY_GENERIC_NOUNS", "category_generic_nouns"),
    )
    max_agent_turns: int = Field(default=40, ge=1, validation_alias=AliasChoices("MAX_AGENT_TURNS", "max_agent_turns"))
    storage_root: Path = Field(
        default=REPO_ROOT / "storage",
        validation_alias=AliasChoices("STORAGE_ROOT", "storage_root"),
    )
    log_level: str = Field(default="INFO", validation_alias=AliasChoices("LOG_LEVEL", "log_level"))

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{REPO_ROOT / 'data' / 'fourthmatch.db'}"

    @property
    def cache_root(self) -> Path:
        return self.storage_root / "cache"

    def model_config_model(self) -> ModelConfig:
        """Validate and return the typed model config; raises naming the missing var."""
        required = {
            "MODEL_API_KEY": self.model_api_key,
            "PERCEPTION_MODEL": self.perception_model,
            "DECISION_MODEL": self.decision_model,
            "COMPILER_MODEL": self.compiler_model,
            "BULK_MODEL": self.bulk_model,
            "SEG_MODEL": self.seg_model,
            "IMAGE_MODEL": self.image_model,
            "VOICE_MODEL": self.voice_model,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValueError(f"Missing required model configuration: {', '.join(missing)}")
        return ModelConfig(
            model_api_key=self.model_api_key,
            meta_base_url=self.meta_base_url,
            perception_model=self.perception_model,
            decision_model=self.decision_model,
            compiler_model=self.compiler_model,
            bulk_model=self.bulk_model,
            wonder_model=self.wonder_model or None,
            seg_model=self.seg_model,
            image_model=self.image_model,
            voice_model=self.voice_model,
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def load_model_config(env: Mapping[str, str] | None = None) -> ModelConfig:
    """Resolve ModelConfig exclusively from config (env mapping or .env via Settings)."""
    if env is None:
        return get_settings().model_config_model()
    merged = dict(os.environ)
    merged.update(env)
    settings = Settings.model_construct(
        model_api_key=merged.get("MODEL_API_KEY", ""),
        meta_base_url=merged.get("META_BASE_URL", "https://api.meta.ai/v1"),
        perception_model=merged.get("PERCEPTION_MODEL", ""),
        decision_model=merged.get("DECISION_MODEL", ""),
        compiler_model=merged.get("COMPILER_MODEL", ""),
        bulk_model=merged.get("BULK_MODEL", ""),
        wonder_model=merged.get("WONDER_MODEL", ""),
        seg_model=merged.get("SEG_MODEL", ""),
        image_model=merged.get("IMAGE_MODEL", ""),
        voice_model=merged.get("VOICE_MODEL", ""),
    )
    return settings.model_config_model()
