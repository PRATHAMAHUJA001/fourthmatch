"""Voice-model ASR over plain HTTP (MODEL_NOTES §6). Never the OpenAI SDK.

POST {meta_base_url}/asr/transcribe, multipart with exactly two parts:
`request` (JSON settings) and `audio` (WAV bytes). Retry with jitter on
network errors / 5xx, never on 4xx. Strict response validation. One
model_calls row per outcome (tokens null: ASR reports none).
"""
from __future__ import annotations

import asyncio
import json
import random
import time

import httpx
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import UpstreamModelError, ValidationError
from app.domain.schemas.config import ModelConfig
from app.domain.schemas.remark import Transcription
from app.infra.cache import Sha256Cache, cache_key_for, sha256_hex
from app.infra.db.models.jobs import ModelCall

MAX_AUDIO_BYTES = 32 * 1024 * 1024
ASR_PURPOSE = "asr_remark"


class MetaTranscriber:
    """Implements domain.protocols.Transcriber."""

    def __init__(
        self,
        config: ModelConfig,
        *,
        session_factory: sessionmaker[Session] | None = None,
        cache: Sha256Cache | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        max_attempts: int = 3,
        timeout_seconds: float = 60.0,
        backoff_base_seconds: float = 0.5,
    ) -> None:
        self._config = config
        self._factory = session_factory
        self._cache = cache
        self._transport = transport
        self._max_attempts = max_attempts
        self._timeout = timeout_seconds
        self._backoff = backoff_base_seconds

    def _write_call(self, *, latency_ms: int | None, status: str, cache_hit: bool,
                    error: str | None = None) -> None:
        if self._factory is None:
            return
        session = self._factory()
        try:
            session.add(ModelCall(
                purpose=ASR_PURPOSE, model=self._config.voice_model, latency_ms=latency_ms,
                input_tokens=None, output_tokens=None, total_tokens=None,
                cache_hit=cache_hit, status=status, error=error, request_meta={"purpose": ASR_PURPOSE},
            ))
            session.commit()
        finally:
            session.close()

    async def transcribe(
        self, *, wav: bytes, filename: str = "remark.wav", session_id: str | None = None
    ) -> Transcription:
        if len(wav) > MAX_AUDIO_BYTES:
            raise ValidationError("remark audio exceeds the 32 MB limit", code="remark_audio_invalid")
        key = cache_key_for(sha256_hex(wav), self._config.voice_model, "asr-v1")
        if self._cache is not None:
            cached = self._cache.get_json(key)
            if cached is not None:
                try:
                    result = Transcription.model_validate(cached)
                except PydanticValidationError:
                    result = None  # corrupt cache entry: fall through to a real call
                if result is not None:
                    self._write_call(latency_ms=0, status="ok", cache_hit=True)
                    return result

        settings = {"model": self._config.voice_model, "audioEncoding": "WAV", "mode": "DIARIZATION"}
        url = f"{self._config.meta_base_url.rstrip('/')}/asr/transcribe"
        params = {"sessionId": session_id} if session_id else None
        headers = {"Authorization": f"Bearer {self._config.model_api_key}", "Accept": "application/json"}
        files: dict[str, tuple[str | None, bytes | str, str]] = {
            "request": (None, json.dumps(settings), "application/json"),
            "audio": (filename, wav, "audio/wav"),
        }
        last_error: str = "unknown"
        async with httpx.AsyncClient(transport=self._transport, timeout=self._timeout) as http:
            for attempt in range(1, self._max_attempts + 1):
                started = time.perf_counter()
                try:
                    resp = await http.post(url, params=params, headers=headers, files=files)
                except httpx.HTTPError as exc:
                    last_error = f"{type(exc).__name__}: {exc}"
                else:
                    latency_ms = int((time.perf_counter() - started) * 1000)
                    if resp.status_code < 400:
                        try:
                            result = Transcription.model_validate(resp.json())
                        except (ValueError, PydanticValidationError) as exc:
                            self._write_call(latency_ms=latency_ms, status="error", cache_hit=False,
                                             error=f"invalid ASR response: {exc}")
                            raise ValidationError(
                                "ASR response failed validation", code="model_output_invalid"
                            ) from exc
                        if self._cache is not None:
                            self._cache.put_json(key, result.model_dump(mode="json", by_alias=True))
                        self._write_call(latency_ms=latency_ms, status="ok", cache_hit=False)
                        return result
                    last_error = f"HTTP {resp.status_code}"
                    if resp.status_code < 500:  # 4xx: never retried
                        self._write_call(latency_ms=latency_ms, status="error", cache_hit=False,
                                         error=last_error)
                        raise UpstreamModelError(
                            f"ASR request rejected ({resp.status_code})", code="asr_rejected"
                        )
                if attempt < self._max_attempts:
                    await asyncio.sleep((2 ** (attempt - 1)) * self._backoff * (0.5 + random.random()))
        self._write_call(latency_ms=None, status="error", cache_hit=False, error=last_error)
        raise UpstreamModelError(f"ASR request failed: {last_error}", code="model_upstream")
