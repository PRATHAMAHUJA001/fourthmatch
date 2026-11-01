"""SAM 3.1 wrapper. Shapes ONLY from docs/MODEL_NOTES.md §4/§5/§8.

- Files API upload once per video hash, file_id cached (storage/cache/files).
  A file-related 400/404 on a cached id invalidates it and re-uploads once.
- Stream is BUFFERED first, parsed OFFLINE with the official meta_sam_parser
  (live parsing stalls socket reads until the server resets the stream).
- Raw events + parsed tracks cached by (video sha256, phrase, seg model,
  proxy fps) under storage/cache/sam -- re-running never re-calls SAM.
- Mask payloads are stored undecoded in a sidecar; mask_ref points into it
  and is decoded only when an overlay actually needs that frame.
"""
from __future__ import annotations

import json
import time
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from meta_sam_parser import (
    decode_mask_to_raster,
    image_segmentation_format,
    parse_responses_stream,
    video_segmentation_format,
)
from openai import APIStatusError, AsyncOpenAI
from PIL import Image
from sqlalchemy.orm import Session

from app.core.errors import UpstreamModelError
from app.core.logging import get_logger
from app.domain.schemas.config import ModelConfig
from app.domain.schemas.perception import BBox, Track, TrackFrame
from app.domain.schemas.sam import ImageSamBox, ImageSegmentation
from app.infra.cache import Sha256Cache, cache_key_for, sha256_hex
from app.infra.db.models.jobs import ModelCall
from app.infra.meta.client import get_shared_client

logger = get_logger(__name__)


async def _stream_events(events: list[dict[str, Any]]) -> AsyncGenerator[dict[str, Any], None]:
    """Cookbook adapter: synthesize response.output_text.done from
    response.content_part.done, which the parser needs to close a lane."""
    completed: set[tuple[Any, Any, Any]] = set()
    for data in events:
        lane = (data.get("item_id"), data.get("output_index"), data.get("content_index"))
        if data.get("type") == "response.output_text.done":
            if lane not in completed:
                completed.add(lane)
                yield data
            continue
        yield data
        part = data.get("part")
        if (
            data.get("type") == "response.content_part.done"
            and lane not in completed
            and isinstance(part, dict)
            and part.get("type") == "output_text"
            and isinstance(part.get("text"), str)
        ):
            completed.add(lane)
            yield {
                "type": "response.output_text.done",
                "item_id": data.get("item_id"),
                "output_index": data.get("output_index"),
                "content_index": data.get("content_index"),
                "text": part["text"],
            }


class SamSegmenter:
    def __init__(self, config: ModelConfig, cache_root: Path, *, client: AsyncOpenAI | None = None) -> None:
        self._config = config
        self._client = client or get_shared_client(config)
        self._files = Sha256Cache(cache_root / "files")
        self._sam = Sha256Cache(cache_root / "sam")
        self._mask_root = cache_root / "masks"
        self._mask_root.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------- Files API
    async def upload_cached(self, data: bytes, filename: str) -> tuple[str, bool]:
        """Upload once per content hash; reuse the cached file_id."""
        key = sha256_hex(data)
        cached = self._files.get_json(key)
        if cached and cached.get("file_id"):
            return str(cached["file_id"]), True
        uploaded = await self._client.files.create(file=(filename, data, "video/mp4"), purpose="user_data")
        file_id = str(uploaded.id)
        assert file_id.startswith("file-"), f"bad file id {file_id!r}"
        self._files.put_json(key, {"file_id": file_id})
        return file_id, False

    def invalidate_file(self, data: bytes) -> None:
        path = self._files.root / f"{sha256_hex(data)}.json"
        path.unlink(missing_ok=True)

    # ------------------------------------------------------------- masks
    def mask_image(self, mask_ref: str) -> tuple[Image.Image, tuple[int, int]] | None:
        """Decode one sidecar mask on demand: (L image, (left, top))."""
        try:
            path_str, key = mask_ref.split(":", 1)
            sidecar = json.loads(Path(path_str).read_text())
            entry = sidecar[key]
            from meta_sam_parser import SegmentationMask

            mask = SegmentationMask(encoding=entry["encoding"], payload=entry["payload"],
                                    width=entry["width"], height=entry["height"])
            raster = decode_mask_to_raster(mask)
            img = Image.frombytes("L", (entry["width"], entry["height"]), bytes(raster))
            bounds = entry["bounds"]
            w, h = max(1, int(bounds[2] - bounds[0])), max(1, int(bounds[3] - bounds[1]))
            return img.resize((w, h)), (int(bounds[0]), int(bounds[1]))
        except Exception:  # overlay must never fail the pipeline on one mask
            return None

    # -------------------------------------------------------- segmentation
    def _write_call(self, session: Session | None, *, latency_ms: int | None, status: str,
                    cache_hit: bool, error: str | None = None, usage: Any | None = None,
                    purpose: str = "sam_segmentation") -> None:
        if session is None:
            return
        session.add(ModelCall(
            purpose=purpose, model=self._config.seg_model, latency_ms=latency_ms,
            input_tokens=getattr(usage, "input_tokens", None) if not isinstance(usage, dict) else usage.get("input_tokens"),
            output_tokens=getattr(usage, "output_tokens", None) if not isinstance(usage, dict) else usage.get("output_tokens"),
            total_tokens=getattr(usage, "total_tokens", None) if not isinstance(usage, dict) else usage.get("total_tokens"),
            cache_hit=cache_hit, status=status, error=error,
            request_meta={"purpose": purpose},
        ))
        session.commit()

    async def segment(
        self,
        *,
        proxy_path: Path,
        phrase: str,
        video_sha256: str,
        proxy_fps: float,
        total_frames: int,
        session: Session | None = None,
    ) -> dict[str, Any]:
        """Returns {tracks, total_frames, cache_hit, raw_cache_path, file_id, sam_key}."""
        sam_key = cache_key_for(video_sha256, phrase, self._config.seg_model, str(proxy_fps))
        cached = self._sam.get_json(sam_key)
        proxy_bytes = proxy_path.read_bytes()
        if cached is not None:
            self._write_call(session, latency_ms=0, status="ok", cache_hit=True)
            logger.info("sam cache hit", extra={"extra_data": {"phrase": phrase, "cache_hit": True}})
            return {
                "tracks": [Track.model_validate(t) for t in cached["tracks"]],
                "total_frames": int(cached.get("total_frames") or total_frames),
                "cache_hit": True,
                "raw_cache_path": cached.get("raw_cache_path"),
                "file_id": cached.get("file_id"),
                "sam_key": sam_key,
            }

        file_id, _ = await self.upload_cached(proxy_bytes, proxy_path.name)
        raw_events: list[dict[str, Any]] | None = None
        started = time.perf_counter()
        for attempt in range(2):  # second attempt only after file re-upload
            try:
                sam_input: Any = [{"type": "message", "role": "user", "content": [
                    {"type": "input_text", "text": phrase},
                    {"type": "input_video", "file_id": file_id},
                ]}]
                stream: Any = await self._client.responses.create(
                    model=self._config.seg_model,
                    stream=True,
                    metadata={"mask_encoding": "one_bit", "include_confidence": "true"},
                    input=sam_input,
                )
                collected: list[dict[str, Any]] = []
                async with stream:
                    async for event in stream:
                        collected.append(event.model_dump() if hasattr(event, "model_dump") else dict(event))
                raw_events = collected
                break
            except APIStatusError as exc:
                if attempt == 0 and exc.status_code in (400, 404) and "file" in str(exc).lower():
                    self.invalidate_file(proxy_bytes)
                    file_id, _ = await self.upload_cached(proxy_bytes, proxy_path.name)
                    continue
                self._write_call(session, latency_ms=int((time.perf_counter() - started) * 1000),
                                 status="error", cache_hit=False, error=str(exc))
                raise UpstreamModelError(f"SAM call failed: {exc}", code="model_upstream") from exc
        assert raw_events is not None
        latency_ms = int((time.perf_counter() - started) * 1000)

        raw_key = cache_key_for(sam_key, "raw-events")
        raw_path = self._sam.put_json(raw_key, raw_events)
        usage = None
        for event in raw_events:
            if event.get("type") == "response.completed":
                usage = (event.get("response") or {}).get("usage")

        from contextlib import aclosing

        async with aclosing(_stream_events(raw_events)) as events:
            result = await parse_responses_stream(events, video_segmentation_format()).final_result()
        if result.outcome.status != "completed":
            self._write_call(session, latency_ms=latency_ms, status="error", cache_hit=False,
                             error=f"SAM incomplete: {result.outcome}", usage=usage)
            raise UpstreamModelError(f"SAM incomplete: {result.outcome}", code="model_upstream")
        errors = [d for d in result.diagnostics if d.severity == "error"]
        if errors:
            self._write_call(session, latency_ms=latency_ms, status="error", cache_hit=False,
                             error=f"SAM parser errors: {errors}", usage=usage)
            raise UpstreamModelError(f"SAM parser errors: {errors}", code="model_upstream")

        # Records -> domain Tracks; mask payloads go to a sidecar, undecoded.
        sidecar: dict[str, Any] = {}
        sidecar_path = self._mask_root / f"{sam_key}.json"
        per_track: dict[str, dict[int, TrackFrame]] = {}
        max_frame = -1
        for rec in result.records:
            if rec.kind == "text" or rec.frame is None:
                continue
            frame_index = int(rec.frame.frame_index)
            max_frame = max(max_frame, frame_index)
            frames = per_track.setdefault(str(rec.object_id), {})
            if rec.kind == "box":
                frames[frame_index] = TrackFrame(
                    frame_index=frame_index,
                    bbox=BBox(x1=float(rec.left), y1=float(rec.top), x2=float(rec.right), y2=float(rec.bottom)),
                    score=getattr(rec, "confidence", None),
                )
            elif rec.kind == "mask":
                key = f"{rec.object_id}:{frame_index}"
                sidecar[key] = {
                    "encoding": str(rec.mask.encoding), "payload": rec.mask.payload,
                    "width": int(rec.mask.width), "height": int(rec.mask.height),
                    "bounds": [float(rec.bounds.left), float(rec.bounds.top),
                               float(rec.bounds.right), float(rec.bounds.bottom)],
                }
                existing = frames.get(frame_index)
                if existing is not None:
                    existing.mask_ref = f"{sidecar_path}:{key}"
        sidecar_path.write_text(json.dumps(sidecar))
        tracks = [
            Track(track_id=oid, phrase=phrase,
                  frames=[frames[k] for k in sorted(frames)])
            for oid, frames in sorted(per_track.items())
        ]
        resolved_total = max(total_frames, max_frame + 1)
        self._sam.put_json(sam_key, {
            "tracks": [t.model_dump() for t in tracks],
            "total_frames": resolved_total,
            "raw_cache_path": str(raw_path),
            "file_id": file_id,
        })
        self._write_call(session, latency_ms=latency_ms, status="ok", cache_hit=False, usage=usage)
        logger.info("sam call ok", extra={"extra_data": {
            "phrase": phrase, "latency_ms": latency_ms, "cache_hit": False,
            "distinct_tracks": len(tracks)}})
        return {
            "tracks": tracks, "total_frames": resolved_total, "cache_hit": False,
            "raw_cache_path": str(raw_path), "file_id": file_id, "sam_key": sam_key,
        }

    # ------------------------------------------------------- still images
    async def segment_image(
        self,
        *,
        image_bytes: bytes,
        mime: str,
        phrase: str,
        session: Session | None = None,
    ) -> ImageSegmentation:
        """SAM on one still (MODEL_NOTES §4): short noun phrase + input_image data URL.

        Raw events are cached by (image sha256, phrase, seg model) under
        storage/cache/sam and re-parsed offline with the official parser, so
        re-running never re-calls SAM.
        """
        import base64
        from contextlib import aclosing

        purpose = "sam_image_segmentation"
        image_sha = sha256_hex(image_bytes)
        raw_key = cache_key_for(image_sha, phrase, self._config.seg_model, "image", "raw-events")
        cached = self._sam.get_json(raw_key)
        latency_ms = 0
        usage: Any = None
        raw_events: list[dict[str, Any]]
        raw_path: Path
        if cached is not None:
            raw_events = cached
            raw_path = self._sam.root / f"{raw_key}.json"
            self._write_call(session, latency_ms=0, status="ok", cache_hit=True, purpose=purpose)
        else:
            data_url = f"data:{mime};base64," + base64.b64encode(image_bytes).decode()
            started = time.perf_counter()
            try:
                sam_input: Any = [{"type": "message", "role": "user", "content": [
                    {"type": "input_text", "text": phrase},
                    {"type": "input_image", "image_url": data_url},
                ]}]
                stream: Any = await self._client.responses.create(
                    model=self._config.seg_model,
                    stream=True,
                    metadata={"mask_encoding": "one_bit", "include_confidence": "true"},
                    input=sam_input,
                )
                collected: list[dict[str, Any]] = []
                async with stream:
                    async for event in stream:
                        collected.append(event.model_dump() if hasattr(event, "model_dump") else dict(event))
            except APIStatusError as exc:
                self._write_call(session, latency_ms=int((time.perf_counter() - started) * 1000),
                                 status="error", cache_hit=False, error=str(exc), purpose=purpose)
                raise UpstreamModelError(f"SAM image call failed: {exc}", code="model_upstream") from exc
            latency_ms = int((time.perf_counter() - started) * 1000)
            raw_events = collected
            for event in raw_events:
                if event.get("type") == "response.completed":
                    usage = (event.get("response") or {}).get("usage")

        async with aclosing(_stream_events(raw_events)) as events:
            result = await parse_responses_stream(events, image_segmentation_format()).final_result()
        errors = [d for d in result.diagnostics if d.severity == "error"]
        if result.outcome.status != "completed" or errors:
            if cached is None:
                self._write_call(session, latency_ms=latency_ms, status="error", cache_hit=False,
                                 error=f"SAM image incomplete: {result.outcome} {errors}", usage=usage,
                                 purpose=purpose)
            raise UpstreamModelError(f"SAM image incomplete: {result.outcome} {errors}", code="model_upstream")
        if cached is None:  # only cache a parse-clean result
            raw_path = self._sam.put_json(raw_key, raw_events)
            self._write_call(session, latency_ms=latency_ms, status="ok", cache_hit=False, usage=usage,
                             purpose=purpose)
        boxes = [
            ImageSamBox(
                object_id=str(rec.object_id), confidence=getattr(rec, "confidence", None),
                left=float(rec.left), top=float(rec.top), right=float(rec.right), bottom=float(rec.bottom),
            )
            for rec in result.records
            if rec.kind == "box"
        ]
        return ImageSegmentation(image_sha256=image_sha, phrase=phrase, boxes=boxes,
                                 cache_hit=cached is not None, raw_cache_path=str(raw_path))
