"""One shared Meta client wrapper.

Request shapes copied ONLY from docs/MODEL_NOTES.md: §2/§3 text + strict
json_schema in text.format, §8 video (input_video file_id) and image crops
(input_image data URLs). Responses API only, never chat.completions.
Every model ID arrives via ModelConfig (core/config.py) — none hardcoded here.
Every call: retry with jitter (no retry on 4xx, except a file-related
400/404 on a cached file_id which raises code=model_file_expired so the
caller can re-upload once), strict JSON, Pydantic validation, model_calls row.
"""
from __future__ import annotations

import asyncio
import base64
import json
import random
import time
from typing import Any, TypeVar

import httpx
from openai import APIStatusError, AsyncOpenAI
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.orm import Session

from app.core.errors import UpstreamModelError, ValidationError
from app.core.logging import get_logger
from app.domain.schemas.config import ModelConfig
from app.domain.schemas.decision_agent import ToolCall, ToolTurn
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
    _strictify(raw)
    return raw


def _strictify(node: Any) -> None:
    """Strict structured output: every object needs additionalProperties=false
    and every property required (verified live: nested objects are checked)."""
    if isinstance(node, dict):
        if node.get("type") == "object" and "properties" in node:
            node["additionalProperties"] = False
            node["required"] = list(node["properties"].keys())
        for value in node.values():
            _strictify(value)
    elif isinstance(node, list):
        for value in node:
            _strictify(value)


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

    async def _execute(
        self,
        *,
        purpose: str,
        model: str,
        input_payload: Any,
        instructions: str | None,
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
                    "input": input_payload,
                    "text": {
                        "format": {
                            "type": "json_schema",
                            "name": output_schema.__name__.lower(),
                            "schema": _strict_json_schema(output_schema),
                            "strict": True,
                        }
                    },
                }
                if instructions:
                    kwargs["instructions"] = instructions
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
                    # Expired/invalid cached file_id (400/404, MODEL_NOTES §8):
                    # caller re-uploads once. Every other 4xx: no retry.
                    if exc.status_code in (400, 404) and "file" in str(exc).lower():
                        self._write_call(session, purpose=purpose, model=model, latency_ms=last_latency_ms,
                                         usage=None, status="error", cache_hit=False, error=str(exc))
                        raise UpstreamModelError(
                            f"cached file_id rejected ({purpose}): {exc}", code="model_file_expired"
                        ) from exc
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
        self,
        *,
        purpose: str,
        model: str,
        prompt: str,
        output_schema: type[T],
        session: Session | None = None,
        reasoning_effort: str | None = None,
        cache_key: str | None = None,
        instructions: str | None = None,
    ) -> T:
        return await self._execute(
            purpose=purpose, model=model, input_payload=prompt, instructions=instructions,
            output_schema=output_schema, session=session,
            reasoning_effort=reasoning_effort, cache_key=cache_key,
        )

    async def call_video_model(
        self,
        *,
        purpose: str,
        model: str,
        instructions: str,
        user_text: str,
        file_id: str,
        output_schema: type[T],
        session: Session | None = None,
        reasoning_effort: str | None = None,
        cache_key: str | None = None,
    ) -> T:
        """Stage B shape (MODEL_NOTES §8): input_video by Files API file_id."""
        input_payload = [{"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": user_text},
            {"type": "input_video", "file_id": file_id},
        ]}]
        return await self._execute(
            purpose=purpose, model=model, input_payload=input_payload, instructions=instructions,
            output_schema=output_schema, session=session,
            reasoning_effort=reasoning_effort, cache_key=cache_key,
        )

    async def call_image_model(
        self,
        *,
        purpose: str,
        model: str,
        instructions: str,
        user_text: str,
        image_data_urls: list[str],
        output_schema: type[T],
        session: Session | None = None,
        reasoning_effort: str | None = None,
        cache_key: str | None = None,
    ) -> T:
        """Stage D shape (MODEL_NOTES §8): labelled input_image crops, one call."""
        content: list[dict[str, Any]] = [{"type": "input_text", "text": user_text}]
        content += [{"type": "input_image", "image_url": url} for url in image_data_urls]
        input_payload = [{"type": "message", "role": "user", "content": content}]
        return await self._execute(
            purpose=purpose, model=model, input_payload=input_payload, instructions=instructions,
            output_schema=output_schema, session=session,
            reasoning_effort=reasoning_effort, cache_key=cache_key,
        )

    async def generate_image(
        self,
        *,
        purpose: str,
        model: str,
        prompt: str,
        session: Session | None = None,
    ) -> bytes:
        """Synthetic test scenes only (MODEL_NOTES §7): images.generate, n=1.

        Returns the raw image bytes exactly as the API sent them (the default
        b64_json payload is WEBP on this key, so callers sniff/transcode).
        Retry with jitter, never on 4xx; one model_calls row per outcome.
        """
        if model not in self._allowed_models():
            raise ValidationError(f"model {model!r} did not come from ModelConfig", code="model_output_invalid")
        last_error: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            started = time.perf_counter()
            try:
                resp = await self._client.images.generate(model=model, prompt=prompt, n=1)
                item = resp.data[0] if resp.data else None
                if item is not None and getattr(item, "b64_json", None):
                    raw = base64.b64decode(str(item.b64_json))
                elif item is not None and getattr(item, "url", None):
                    async with httpx.AsyncClient(timeout=120) as http:
                        fetched = await http.get(str(item.url))
                        fetched.raise_for_status()
                        raw = fetched.content
                else:
                    raise UpstreamModelError("image response had neither b64_json nor url", code="model_upstream")
                latency_ms = int((time.perf_counter() - started) * 1000)
                self._write_call(session, purpose=purpose, model=model, latency_ms=latency_ms,
                                 usage=getattr(resp, "usage", None), status="ok", cache_hit=False)
                logger.info("model call ok", extra={"extra_data": {
                    "model": model, "latency_ms": latency_ms, "purpose": purpose, "cache_hit": False}})
                return raw
            except UpstreamModelError:
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
        self._write_call(session, purpose=purpose, model=model, latency_ms=None, usage=None,
                         status="error", cache_hit=False, error=str(last_error))
        raise UpstreamModelError(f"model call failed ({purpose}): {last_error}", code="model_upstream")

    async def call_tool_turn(
        self,
        *,
        purpose: str,
        model: str,
        instructions: str,
        input_items: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        session: Session | None = None,
        reasoning_effort: str | None = "high",
    ) -> ToolTurn:
        """One turn of the tool-calling loop, stateless replay (MODEL_NOTES §3).

        The caller replays prior ``output_items`` plus ``function_call_output``
        items in ``input_items``. include=reasoning.encrypted_content is always
        sent and previous_response_id never is (verified 400 otherwise).
        Retry with jitter, never on 4xx; one model_calls row per turn.
        """
        if model not in self._allowed_models():
            raise ValidationError(
                f"model {model!r} did not come from ModelConfig", code="model_output_invalid"
            )
        last_error: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            started = time.perf_counter()
            try:
                kwargs: dict[str, Any] = {
                    "model": model,
                    "instructions": instructions,
                    "input": input_items,
                    "tools": tools,
                    "include": ["reasoning.encrypted_content"],
                }
                if reasoning_effort:
                    kwargs["reasoning"] = {"effort": reasoning_effort}
                resp = await self._client.responses.create(**kwargs)
                latency_ms = int((time.perf_counter() - started) * 1000)
                items = list(resp.output)
                turn = ToolTurn(
                    output_items=[item.model_dump() for item in items],
                    calls=[
                        ToolCall(name=item.name, arguments=item.arguments, call_id=item.call_id)
                        for item in items
                        if getattr(item, "type", None) == "function_call"
                    ],
                    output_text=getattr(resp, "output_text", "") or "",
                )
                self._write_call(session, purpose=purpose, model=model, latency_ms=latency_ms,
                                 usage=getattr(resp, "usage", None), status="ok", cache_hit=False)
                logger.info("model call ok", extra={"extra_data": {
                    "model": model, "latency_ms": latency_ms, "purpose": purpose,
                    "input_tokens": getattr(getattr(resp, "usage", None), "input_tokens", None),
                    "output_tokens": getattr(getattr(resp, "usage", None), "output_tokens", None),
                    "cache_hit": False}})
                return turn
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
        self._write_call(session, purpose=purpose, model=model, latency_ms=None, usage=None,
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
