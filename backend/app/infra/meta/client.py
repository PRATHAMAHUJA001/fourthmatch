"""One shared Meta client wrapper.

Request shapes copied ONLY from docs/MODEL_NOTES.md §2/§3 (Responses API,
strict json_schema in text.format, reasoning, never chat.completions).
Every model ID arrives via ModelConfig (core/config.py) — none hardcoded here.
"""
from __future__ import annotations

import asyncio
import json
import random
import time
from typing import Any, TypeVar

from openai import APIStatusError, AsyncOpenAI
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.orm import Session

from app.core.errors import UpstreamModelError, ValidationError
from app.core.logging import get_logger
from app.domain.schemas.config import ModelConfig
from app.infra.cache import Sha256Cache
from app.infra.db.models.jobs import ModelCall

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)

_shared_client: AsyncOpenAI | None = None


def get_shared_client(config: ModelConfig) -> AsyncOpenAI:
    global _shared_client
    if _shared_client is None:
        _shared_client = AsyncOpenAI(base_url=config.meta_base_url, api_key=config.model_api_key)
    return _shared_client


def _strict_json_schema(schema: type[BaseModel]) -> dict[str, Any]:
    raw = schema.model_json_schema()
    raw.setdefault("type", "object")
    raw["additionalProperties"] = False
    if raw.get("type") == "object" and "properties" in raw:
        raw["required"] = list(raw["properties"].keys())
    return raw


class MetaModelClient:
    """Retry+jitter (no retry on 4xx), strict JSON, Pydantic validation, model_calls row."""

    def __init__(
        self,
        config: ModelConfig,
        *,
        client: AsyncOpenAI | None = None,
        cache: Sha256Cache | None = None,
        max_attempts: int = 3,
    ) -> None:
        self._config = config
        self._client = client or get_shared_client(config)
        self._cache = cache
        self._max_attempts = max_attempts

    def _allowed_models(self) -> set[str]:
        values = {
            self._config.perception_model,
            self._config.decision_model,
            self._config.compiler_model,
            self._config.bulk_model,
            self._config.seg_model,
            self._config.image_model,
            self._config.voice_model,
        }
        if self._config.wonder_model:
            values.add(self._config.wonder_model)
        return values

    def _write_call(
        self,
        session: Session | None,
        *,
        purpose: str,
        model: str,
        latency_ms: int | None,
        usage: Any | None,
        status: str,
        cache_hit: bool,
        error: str | None = None,
    ) -> None:
        if session is None:
            return
        session.add(
            ModelCall(
                purpose=purpose,
                model=model,
                latency_ms=latency_ms,
                input_tokens=getattr(usage, "input_tokens", None),
                output_tokens=getattr(usage, "output_tokens", None),
                total_tokens=getattr(usage, "total_tokens", None),
                cache_hit=cache_hit,
                status=status,
                error=error,
                request_meta={"purpose": purpose},
            )
        )
        session.commit()

    async def call_model(
        self,
        *,
        purpose: str,
        model: str,
        prompt: str,
        output_schema: type[T],
        session: Session | None = None,
        reasoning_effort: str | None = None,
        cache_key: str | None = None,
    ) -> T:
        if model not in self._allowed_models():
            raise ValidationError(
                f"model {model!r} did not come from ModelConfig",
                code="model_output_invalid",
            )

        if cache_key and self._cache is not None:
            cached = self._cache.get_json(cache_key)
            if cached is not None:
                try:
                    parsed_cached = output_schema.model_validate(cached)
                except PydanticValidationError as exc:
                    raise ValidationError(f"cached model output invalid: {exc}", code="model_output_invalid") from exc
                self._write_call(session, purpose=purpose, model=model, latency_ms=0, usage=None,
                                 status="ok", cache_hit=True)
                logger.info("model call cache hit", extra={"extra_data": {
                    "model": model, "latency_ms": 0, "cache_hit": True, "purpose": purpose}})
                return parsed_cached

        last_error: Exception | None = None
        last_latency_ms: int | None = None
        for attempt in range(1, self._max_attempts + 1):
            started = time.perf_counter()
            try:
                kwargs: dict[str, Any] = {
                    "model": model,
                    "input": prompt,
                    "text": {
                        "format": {
                            "type": "json_schema",
                            "name": output_schema.__name__.lower(),
                            "schema": _strict_json_schema(output_schema),
                            "strict": True,
                        }
                    },
                }
                if reasoning_effort:
                    kwargs["reasoning"] = {"effort": reasoning_effort}
                resp = await self._client.responses.create(**kwargs)
                latency_ms = int((time.perf_counter() - started) * 1000)
                last_latency_ms = latency_ms
                try:
                    data = json.loads(resp.output_text)  # strict parse; raises if invalid
                    parsed = output_schema.model_validate(data)
                except (json.JSONDecodeError, PydanticValidationError) as exc:
                    self._write_call(session, purpose=purpose, model=model, latency_ms=latency_ms,
                                     usage=getattr(resp, "usage", None), status="error",
                                     cache_hit=False, error=str(exc))
                    raise ValidationError(f"model output invalid: {exc}", code="model_output_invalid") from exc
                self._write_call(session, purpose=purpose, model=model, latency_ms=latency_ms,
                                 usage=getattr(resp, "usage", None), status="ok", cache_hit=False)
                logger.info("model call ok", extra={"extra_data": {
                    "model": model, "latency_ms": latency_ms,
                    "input_tokens": getattr(getattr(resp, "usage", None), "input_tokens", None),
                    "output_tokens": getattr(getattr(resp, "usage", None), "output_tokens", None),
                    "cache_hit": False, "purpose": purpose}})
                if cache_key and self._cache is not None:
                    self._cache.put_json(cache_key, data)
                return parsed
            except ValidationError:
                raise
            except APIStatusError as exc:
                last_error = exc
                if 400 <= exc.status_code < 500:
                    break  # never retry 4xx
                if attempt < self._max_attempts:
                    await asyncio.sleep((2 ** (attempt - 1)) * 0.5 * (0.5 + random.random()))
            except Exception as exc:  # connection / 5xx style failures: retry with jitter
                last_error = exc
                if attempt < self._max_attempts:
                    await asyncio.sleep((2 ** (attempt - 1)) * 0.5 * (0.5 + random.random()))

        self._write_call(session, purpose=purpose, model=model, latency_ms=last_latency_ms, usage=None,
                         status="error", cache_hit=False, error=str(last_error))
        raise UpstreamModelError(f"model call failed ({purpose}): {last_error}", code="model_upstream")


async def call_model(
    client: MetaModelClient,
    *,
    session: Session | None = None,
    **kwargs: Any,
) -> BaseModel:
    """Functional wrapper around MetaModelClient.call_model (see ARCHITECTURE §6)."""
    return await client.call_model(session=session, **kwargs)
