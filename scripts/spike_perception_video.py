#!/usr/bin/env python3
"""Spike: verify Spark (PERCEPTION_MODEL) video + image-crop request shapes.

Not in MODEL_NOTES yet -- this script verifies, live:
 1. Files API upload of a 2fps proxy, reuse file_id for Spark input_video
    with strict structured JSON (Stage B shape).
 2. Bogus/expired file_id error shape (for the re-upload-on-404 path).
 3. Spark input_image crops (data URLs) with strict structured JSON
    (Stage D shape), multiple labelled crops in one call.

Usage: backend/.venv/bin/python scripts/spike_perception_video.py
Reads all model IDs / key from repo-root .env (never hardcoded).
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

UNDERSTANDING_SCHEMA = {
    "type": "object",
    "properties": {
        "lines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "po_line_id": {"type": "string"},
                    "noun_phrase": {"type": "string"},
                    "distinguishing_feature": {"type": ["string", "null"]},
                },
                "required": ["po_line_id", "noun_phrase", "distinguishing_feature"],
                "additionalProperties": False,
            },
        },
        "scene": {
            "type": "object",
            "properties": {
                "camera_motion": {"type": "string", "enum": ["static", "pan", "handheld"]},
                "occlusion": {"type": "string", "enum": ["none", "partial", "heavy"]},
                "lighting": {"type": "string", "enum": ["good", "poor"]},
                "unlisted_objects": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["camera_motion", "occlusion", "lighting", "unlisted_objects"],
            "additionalProperties": False,
        },
    },
    "required": ["lines", "scene"],
    "additionalProperties": False,
}

DAMAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "track_id": {"type": "string"},
        "damaged": {"type": "boolean"},
        "frame_index": {"type": ["integer", "null"]},
        "note": {"type": "string"},
    },
    "required": ["track_id", "damaged", "frame_index", "note"],
    "additionalProperties": False,
}


def req(name: str) -> str:
    v = os.environ.get(name, "").strip()
    if not v:
        raise RuntimeError(f"{name} not set in .env")
    return v


async def main() -> int:
    client = AsyncOpenAI(base_url=os.environ.get("META_BASE_URL", "https://api.meta.ai/v1"),
                         api_key=req("MODEL_API_KEY"))
    perception = req("PERCEPTION_MODEL")
    src = ROOT / "samples" / "scenarios" / "scn1_clean.mp4"

    with tempfile.TemporaryDirectory() as tmp:
        proxy = Path(tmp) / "proxy.mp4"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vf", "fps=2",
                        "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(proxy)],
                       check=True, capture_output=True, text=True)
        proxy_bytes = proxy.read_bytes()

        # --- 1. Files API upload + Spark input_video + structured JSON
        t0 = time.perf_counter()
        uploaded = await client.files.create(file=("scn1_clean.mp4", proxy_bytes, "video/mp4"),
                                             purpose="user_data")
        file_id = uploaded.id
        print(f"UPLOAD ok file_id={file_id} type={type(file_id).__name__} "
              f"bytes={len(proxy_bytes)} ({time.perf_counter()-t0:.1f}s)", flush=True)
        assert file_id.startswith("file-")

        t0 = time.perf_counter()
        try:
            resp = await client.responses.create(
                model=perception,
                instructions=(
                    "You are FourthMatch's receiving-dock perception agent. You get a "
                    "receiving-dock video and the purchase-order lines that should be in it. "
                    "Pick one short noun phrase per line and state scene facts. Never count. "
                    "Return only JSON."),
                input=[{"type": "message", "role": "user", "content": [
                    {"type": "input_text", "text": (
                        'PO lines: [{"po_line_id": "7", "category": "cartons", '
                        '"description": "Cardboard carton boxes"}]. Return JSON.')},
                    {"type": "input_video", "file_id": file_id},
                ]}],
                text={"format": {"type": "json_schema", "name": "understanding",
                                 "schema": UNDERSTANDING_SCHEMA, "strict": True}},
            )
            data = json.loads(resp.output_text)
            print(f"STAGE_B ok ({time.perf_counter()-t0:.1f}s) usage={resp.usage}\n  {data}", flush=True)
            assert data["lines"] and data["scene"]
        except Exception as exc:
            print(f"STAGE_B FAIL ({time.perf_counter()-t0:.1f}s) {type(exc).__name__}: {exc}", flush=True)
            # Try alternate shape: video_url? report and bail
            raise

        # --- 2. bogus file_id error shape
        try:
            await client.responses.create(
                model=perception,
                input=[{"type": "message", "role": "user", "content": [
                    {"type": "input_text", "text": "hi"},
                    {"type": "input_video", "file_id": "file-doesnotexist000"},
                ]}],
            )
            print("BOGUS_FILE unexpected success", flush=True)
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            print(f"BOGUS_FILE error status={status} type={type(exc).__name__}: {str(exc)[:300]}", flush=True)

        # --- 3. Stage D: labelled image crops in one call
        frame_png = Path(tmp) / "frame.png"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(proxy), "-vf", "select=eq(n\\,10)",
                        "-vframes", "1", str(frame_png)], check=True, capture_output=True, text=True)
        img = Image.open(frame_png).convert("RGB")
        crops = []
        labels = []
        for i, box in enumerate([(0, 0, img.width // 2, img.height), (img.width // 2, 0, img.width, img.height)]):
            crop = img.crop(box)
            buf = io.BytesIO()
            crop.save(buf, format="PNG")
            crops.append(f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}")
            labels.append(f"track_id=T1 frame_index={5 + i}")
        content: list[dict] = [{"type": "input_text", "text": (
            "Inspect crops of ONE tracked object. track_id=T1. "
            f"Crop labels in order: {labels}. Return JSON for track_id T1.")}]
        for url in crops:
            content.append({"type": "input_image", "image_url": url})
        t0 = time.perf_counter()
        resp = await client.responses.create(
            model=perception,
            instructions=("You inspect crops of ONE tracked object. Decide if visibly damaged. "
                          "Return only JSON."),
            input=[{"type": "message", "role": "user", "content": content}],
            text={"format": {"type": "json_schema", "name": "damage_verdict",
                             "schema": DAMAGE_SCHEMA, "strict": True}},
        )
        data = json.loads(resp.output_text)
        print(f"STAGE_D ok ({time.perf_counter()-t0:.1f}s) usage={resp.usage}\n  {data}", flush=True)
        assert data["track_id"] == "T1"
    print("SPIKE PASS")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
