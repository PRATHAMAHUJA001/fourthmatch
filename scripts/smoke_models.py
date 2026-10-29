#!/usr/bin/env python3
"""Smoke-test every Meta model FourthMatch depends on. No mocks.

Usage: backend/.venv/bin/python scripts/smoke_models.py
Reads MODEL_API_KEY + all model IDs from the repo-root .env (never hardcoded).
Prints PASS/FAIL + latency per check; exit code 0 only if all 7 pass.
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import mimetypes
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import aclosing
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from meta_sam_parser import (
    decode_mask_to_raster,
    image_segmentation_format,
    parse_responses_stream,
    video_segmentation_format,
)
from openai import AsyncOpenAI
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

BASE_URL = os.environ.get("META_BASE_URL", "https://api.meta.ai/v1")
API_KEY = os.environ.get("MODEL_API_KEY", "")


def req_env(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        raise RuntimeError(f"{name} is not set in .env")
    return val


def models_from_env() -> dict[str, str]:
    return {
        "spark": req_env("PERCEPTION_MODEL"),
        "decision": req_env("DECISION_MODEL"),
        "wonder": req_env("WONDER_MODEL"),
        "seg": req_env("SEG_MODEL"),
        "image": req_env("IMAGE_MODEL"),
        "voice": req_env("VOICE_MODEL"),
    }


def client() -> AsyncOpenAI:
    if not API_KEY:
        raise RuntimeError("MODEL_API_KEY is not set in .env")
    return AsyncOpenAI(base_url=BASE_URL, api_key=API_KEY)


RESULTS: list[tuple[str, bool, float, str]] = []


async def check(name: str, fn) -> bool:
    start = time.perf_counter()
    try:
        detail = await fn()
        dt = time.perf_counter() - start
        print(f"PASS {name} ({dt:.2f}s) {detail or ''}", flush=True)
        RESULTS.append((name, True, dt, detail or ""))
        return True
    except Exception as exc:  # noqa: BLE001 - smoke script must report, not crash
        dt = time.perf_counter() - start
        print(f"FAIL {name} ({dt:.2f}s) {type(exc).__name__}: {exc}", flush=True)
        RESULTS.append((name, False, dt, f"{type(exc).__name__}: {exc}"))
        return False


# ---------------------------------------------------------------- 1. models
async def check_models(m: dict[str, str]) -> str:
    async with httpx.AsyncClient(timeout=60) as http:
        r = await http.get(
            f"{BASE_URL}/models",
            headers={"Authorization": f"Bearer {API_KEY}"},
        )
        r.raise_for_status()
        payload = r.json()
    ids = {item["id"] for item in payload.get("data", []) if "id" in item}
    expected = {m["spark"], m["wonder"], m["seg"], m["image"], m["voice"]}
    missing = expected - ids
    assert not missing, f"missing models: {sorted(missing)}; got {sorted(ids)}"
    return f"{len(ids)} models listed; all {len(expected)} expected present: {sorted(expected)}"


# ------------------------------------------------------- 2. structured JSON
async def check_structured(m: dict[str, str]) -> str:
    async with client() as api:
        resp = await api.responses.create(
            model=m["decision"],
            reasoning={"effort": "high"},
            input="Confirm the smoke test: set ok to true and message to 'pong'.",
            text={
                "format": {
                    "type": "json_schema",
                    "name": "smoke_check",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "ok": {"type": "boolean"},
                            "message": {"type": "string"},
                        },
                        "required": ["ok", "message"],
                        "additionalProperties": False,
                    },
                    "strict": True,
                }
            },
        )
    data = json.loads(resp.output_text)  # strict parse; raises if not JSON
    assert data.get("ok") is True, f"unexpected payload: {data}"
    usage = getattr(resp, "usage", None)
    return f"json={data} usage={usage}"


# ------------------------------------------------------------ 3. tool loop
def compute_variance(a: float, b: float) -> dict[str, float]:
    """Dummy tool: all arithmetic in Python, never in the LLM."""
    variance = a - b
    variance_pct = (variance / a * 100.0) if a else 0.0
    return {"variance": variance, "variance_pct": round(variance_pct, 4)}


async def check_tool_loop(m: dict[str, str]) -> str:
    tools = [
        {
            "type": "function",
            "name": "compute_variance",
            "description": "Compute variance between ordered qty a and received qty b.",
            "parameters": {
                "type": "object",
                "properties": {
                    "a": {"type": "number", "description": "Ordered quantity"},
                    "b": {"type": "number", "description": "Received quantity"},
                },
                "required": ["a", "b"],
                "additionalProperties": False,
            },
            "strict": True,
        }
    ]
    called: list[dict[str, Any]] = []
    async with client() as api:
        resp = await api.responses.create(
            model=m["decision"],
            reasoning={"effort": "high"},
            include=["reasoning.encrypted_content"],
            tools=tools,
            input=(
                "A PO ordered 100 cartons and the dock received 87 cartons. "
                "You must call compute_variance with a=100 and b=87, then report "
                "the variance and variance_pct from the tool result."
            ),
        )
        for _ in range(5):
            calls = [i for i in resp.output if getattr(i, "type", None) == "function_call"]
            if not calls:
                break
            outputs = []
            for item in calls:
                args = json.loads(item.arguments)
                assert item.name == "compute_variance", f"unexpected tool {item.name}"
                result = compute_variance(**args)
                called.append({"args": args, "result": result})
                outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": item.call_id,
                        "output": json.dumps(result),
                    }
                )
            resp = await api.responses.create(
                model=m["decision"],
                reasoning={"effort": "high"},
                include=["reasoning.encrypted_content"],
                tools=tools,
                # Stateless replay: the API rejects include=["reasoning.encrypted_content"]
                # together with previous_response_id (400), so replay the prior
                # output items (reasoning + function_call) plus the tool outputs.
                input=[
                    *(item.model_dump() for item in resp.output),
                    *outputs,
                ],
            )
    assert called, "model never called compute_variance"
    assert called[0]["result"]["variance"] == 13, f"wrong variance: {called}"
    final = resp.output_text or ""
    assert "13" in final, f"final answer does not cite tool result: {final!r}"
    return f"tool_calls={called} final={final.strip()[:160]!r}"


# ------------------------------------------------------------------ SAM util
async def stream_events(stream):
    """Cookbook adapter: synthesize response.output_text.done from
    response.content_part.done, which the parser needs to close a lane."""
    completed: set[tuple[Any, Any, Any]] = set()
    async for event in stream:
        data = event.model_dump() if hasattr(event, "model_dump") else dict(event)
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


def sam_input(prompt: str, media: dict[str, str]) -> list[dict[str, Any]]:
    return [
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": prompt}, media],
        }
    ]


def validate_sam(result) -> None:
    if result.outcome.status != "completed":
        raise RuntimeError(f"SAM incomplete: {result.outcome}")
    errors = [d for d in result.diagnostics if d.severity == "error"]
    if errors:
        raise RuntimeError(f"SAM parser errors: {errors}")


# ------------------------------------------------------------- 4. SAM image
async def check_sam_image(m: dict[str, str]) -> str:
    # Task names samples/carton.jpg; the file on disk is samples/cartoon.jpg
    # (PNG bytes despite the .jpg name). Accept either, prefer carton.jpg.
    path = ROOT / "samples" / "carton.jpg"
    if not path.exists():
        path = ROOT / "samples" / "cartoon.jpg"
    assert path.exists(), "neither samples/carton.jpg nor samples/cartoon.jpg exists"

    pil = Image.open(path)
    mime = f"image/{pil.format.lower()}" if pil.format else "image/png"
    buf = io.BytesIO()
    pil.save(buf, format=pil.format or "PNG")
    data_url = f"data:{mime};base64," + base64.b64encode(buf.getvalue()).decode()

    async with client() as api:
        stream = await api.responses.create(
            model=m["seg"],
            stream=True,
            input=sam_input("cardboard box", {"type": "input_image", "image_url": data_url}),
        )
        async with stream, aclosing(stream_events(stream)) as events:
            result = await parse_responses_stream(
                events, image_segmentation_format()
            ).final_result()
    validate_sam(result)
    boxes = [r for r in result.records if r.kind == "box"]
    masks = [r for r in result.records if r.kind == "mask"]
    box_list = [
        {
            "object_id": b.object_id,
            "left": b.left,
            "top": b.top,
            "right": b.right,
            "bottom": b.bottom,
        }
        for b in boxes
    ]

    # Overlay: masks (translucent) + box outlines, saved as PNG evidence sample.
    out_dir = ROOT / "samples" / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    overlay = pil.convert("RGB")
    tint = Image.new("RGB", overlay.size, (255, 0, 0))
    for rec in masks:
        raster = decode_mask_to_raster(rec.mask)
        mask_img = Image.frombytes("L", (rec.mask.width, rec.mask.height), bytes(raster))
        w = max(1, int(rec.bounds.right - rec.bounds.left))
        h = max(1, int(rec.bounds.bottom - rec.bounds.top))
        mask_img = mask_img.resize((w, h))
        overlay.paste(
            Image.blend(
                overlay.crop(
                    (
                        int(rec.bounds.left),
                        int(rec.bounds.top),
                        int(rec.bounds.left) + w,
                        int(rec.bounds.top) + h,
                    )
                ),
                tint.crop((0, 0, w, h)),
                0.35,
            ),
            (int(rec.bounds.left), int(rec.bounds.top)),
            mask_img.point(lambda v: 128 if v else 0),
        )
    draw = ImageDraw.Draw(overlay)
    for b in boxes:
        draw.rectangle([b.left, b.top, b.right, b.bottom], outline=(255, 0, 0), width=4)
        draw.text((b.left + 2, max(0, b.top - 14)), str(b.object_id), fill=(255, 0, 0))
    out_path = out_dir / "carton_overlay.png"
    overlay.save(out_path, format="PNG")
    assert out_path.exists() and out_path.stat().st_size > 0
    return (
        f"file={path.name} count={len(boxes)} boxes={box_list} "
        f"masks={len(masks)} overlay={out_path.relative_to(ROOT)}"
    )


# ------------------------------------------------------------- 5. SAM video
async def check_sam_video(m: dict[str, str]) -> str:
    path = ROOT / "samples" / "dock.mp4"
    assert path.exists(), "samples/dock.mp4 missing"
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg, "ffmpeg is required to prepare the SAM video proxy"

    # Why a proxy: the Meta API itself streams all 265 frames of the 24 fps
    # original in ~18 s, but meta_sam_parser raster-decodes every mask to
    # validate it (~0.2 s/mask, pure Python): 2,251 masks = ~518 s of parser
    # CPU, which stalls the socket until the server resets the stream.
    # The cartons are near-static, so a 2 fps ffmpeg proxy of dock.mp4 keeps
    # every track (verified: same 10 distinct tracks at 24, 5 and 2 fps)
    # while cutting the stream to 22 frames / ~374 records (~41 s parse).
    with tempfile.TemporaryDirectory() as tmp:
        proxy = Path(tmp) / "dock_proxy_2fps.mp4"
        subprocess.run(
            [
                ffmpeg, "-y", "-v", "error", "-i", str(path),
                "-vf", "fps=2", "-an", "-c:v", "libx264",
                "-pix_fmt", "yuv420p", str(proxy),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        mime = mimetypes.guess_type(proxy.name)[0] or "video/mp4"
        proxy_bytes = proxy.read_bytes()

    async with client() as api:
        # Upload once via the Files API, reuse file_id across retries.
        uploaded = await api.files.create(
            file=("dock.mp4", proxy_bytes, mime), purpose="user_data"
        )
        file_id = uploaded.id
        assert isinstance(file_id, str) and file_id.startswith("file-"), f"bad file id {file_id!r}"

        # Drain the stream WITHOUT the parser in the loop: collecting SDK
        # events is cheap, so the socket never stalls. Retry with jitter on
        # connection errors / 5xx only (never 4xx), same file_id.
        raw_events: list[dict[str, Any]] | None = None
        for attempt in range(1, 4):
            try:
                stream = await api.responses.create(
                    model=m["seg"],
                    stream=True,
                    # one_bit masks keep the per-frame payload small (docs:
                    # metadata={"mask_encoding": "one_bit"}); lossless is heavy.
                    metadata={"mask_encoding": "one_bit"},
                    input=sam_input(
                        "cardboard box", {"type": "input_video", "file_id": file_id}
                    ),
                )
                collected: list[dict[str, Any]] = []
                async with stream:
                    async for event in stream:
                        collected.append(
                            event.model_dump()
                            if hasattr(event, "model_dump")
                            else dict(event)
                        )
                raw_events = collected
                break
            except Exception as exc:  # noqa: BLE001 - re-raised below when fatal
                status = getattr(exc, "status_code", None) or getattr(
                    getattr(exc, "response", None), "status_code", None
                )
                if (status is not None and 400 <= status < 500) or attempt == 3:
                    raise
                wait = 2**attempt + random.uniform(0, 1)
                print(
                    f"  sam_video attempt={attempt} drain failed "
                    f"({type(exc).__name__}: {exc}); retrying in {wait:.1f}s "
                    f"with same file_id",
                    flush=True,
                )
                await asyncio.sleep(wait)
        assert raw_events is not None

    # Parse the buffered events with the official parser, offline.
    async def replay(events: list[dict[str, Any]]):
        for event in events:
            yield event

    async with aclosing(stream_events(replay(raw_events))) as events:
        result = await parse_responses_stream(
            events, video_segmentation_format()
        ).final_result()
    validate_sam(result)
    tracks: dict[str, list[int]] = {}
    for rec in result.records:
        if rec.frame is not None:
            tracks.setdefault(rec.object_id, []).append(rec.frame.frame_index)
    track_summary = {
        oid: {"first": min(f), "last": max(f), "visible_frames": len(set(f))}
        for oid, f in sorted(tracks.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else kv[0])
    }
    return (
        f"source=dock.mp4 proxy_fps=2 file_id={file_id} "
        f"distinct_tracks={len(tracks)} tracks={track_summary}"
    )


# -------------------------------------------------------------------- 6. ASR
async def check_asr(m: dict[str, str]) -> str:
    path = ROOT / "samples" / "remark.wav"
    assert path.exists(), "samples/remark.wav missing"
    settings = {"model": m["voice"], "audioEncoding": "WAV", "mode": "DIARIZATION"}
    async with httpx.AsyncClient(timeout=180) as http:
        r = await http.post(
            f"{BASE_URL}/asr/transcribe",
            params={"sessionId": "smoke-remark"},
            headers={"Authorization": f"Bearer {API_KEY}", "Accept": "application/json"},
            files={
                "request": (None, json.dumps(settings), "application/json"),
                "audio": (path.name, path.read_bytes(), "audio/wav"),
            },
        )
        if r.status_code >= 400:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:500]}")
        payload = r.json()
    transcript = payload.get("transcript") or ""
    if not transcript and payload.get("turns"):
        transcript = " ".join(t.get("text", "") for t in payload["turns"]).strip()
    assert transcript, f"empty transcript; response keys={list(payload)} body={str(payload)[:400]}"
    return f"transcript={transcript!r} turns={len(payload.get('turns', []))}"


# ------------------------------------------------------------- 7. image gen
async def check_image_gen(m: dict[str, str]) -> str:
    out_dir = ROOT / "samples" / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "gen.png"
    async with client() as api:
        resp = await api.images.generate(
            model=m["image"],
            prompt="warehouse receiving dock with 18 steel coils, CCTV angle",
            n=1,
        )
    item = resp.data[0]
    if getattr(item, "b64_json", None):
        raw = base64.b64decode(item.b64_json)
    elif getattr(item, "url", None):
        async with httpx.AsyncClient(timeout=120) as http:
            r = await http.get(item.url)
            r.raise_for_status()
            raw = r.content
    else:
        raise RuntimeError(f"no b64_json or url in image response: {item}")
    # API may return WEBP bytes even for a .png target; transcode so gen.png
    # is a genuine PNG on disk.
    src = Image.open(io.BytesIO(raw))
    src_format = src.format
    src.load()
    src.save(out_path, format="PNG")
    img = Image.open(out_path)
    img.verify()
    return (
        f"saved={out_path.relative_to(ROOT)} bytes={out_path.stat().st_size} "
        f"format={img.format} size={img.size} api_format={src_format}"
    )


async def main() -> int:
    if not API_KEY:
        print("FAIL setup (0.00s) MODEL_API_KEY is not set in .env", flush=True)
        return 1
    m = models_from_env()
    print(f"base_url={BASE_URL} models={m}", flush=True)
    await check("1_models_list", lambda: check_models(m))
    await check("2_spark_structured_json", lambda: check_structured(m))
    await check("3_spark_tool_loop", lambda: check_tool_loop(m))
    await check("4_sam_image", lambda: check_sam_image(m))
    await check("5_sam_video", lambda: check_sam_video(m))
    await check("6_asr_transcribe", lambda: check_asr(m))
    await check("7_image_generate", lambda: check_image_gen(m))
    passed = sum(1 for _, ok, _, _ in RESULTS if ok)
    print(f"SUMMARY {passed}/{len(RESULTS)} PASS", flush=True)
    for name, ok, dt, detail in RESULTS:
        print(f"  {'PASS' if ok else 'FAIL'} {name} {dt:.2f}s {detail[:200]}", flush=True)
    return 0 if passed == len(RESULTS) == 7 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
