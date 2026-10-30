"""ffmpeg/Pillow helpers: proxy, frames, crops, overlays, annotated MP4.

No model calls here. All frame indices refer to the proxy video (SAM_PROXY_FPS)
consistently across SAM, crops and overlays.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

from app.domain.schemas.perception import BBox, Track

_COLORS = [(255, 80, 80), (80, 200, 120), (80, 140, 255), (255, 190, 60),
           (200, 100, 255), (60, 210, 210), (255, 120, 200), (150, 220, 80)]


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def probe_video(path: Path) -> tuple[int, int, int]:
    """(width, height, frame_count) via ffprobe frame counting."""
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,nb_read_frames", "-of", "json", str(path)],
        check=True, capture_output=True, text=True,
    )
    stream = json.loads(r.stdout)["streams"][0]
    return int(stream["width"]), int(stream["height"]), int(stream["nb_read_frames"])


def make_proxy(src: Path, dst: Path, fps: float) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    _run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vf", f"fps={fps}",
          "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(dst)])
    return dst


def extract_frames(video: Path, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(out_dir.glob("frame_*.png"))
    if existing:
        return existing
    _run(["ffmpeg", "-y", "-v", "error", "-i", str(video), str(out_dir / "frame_%04d.png")])
    return sorted(out_dir.glob("frame_*.png"))


def crop_data_url(frame_path: Path, bbox: BBox, *, pad: int = 24) -> tuple[str, str]:
    """Crop bbox (+pad) from a frame. Returns (data_url, sha256 of PNG bytes)."""
    img = Image.open(frame_path).convert("RGB")
    x1 = max(0, int(bbox.x1) - pad)
    y1 = max(0, int(bbox.y1) - pad)
    x2 = min(img.width, int(bbox.x2) + pad)
    y2 = min(img.height, int(bbox.y2) + pad)
    crop = img.crop((x1, y1, x2, y2))
    buf = io.BytesIO()
    crop.save(buf, format="PNG")
    data = buf.getvalue()
    return f"data:image/png;base64,{base64.b64encode(data).decode()}", hashlib.sha256(data).hexdigest()


def render_overlay_frames(
    frame_paths: list[Path],
    tracks: list[Track],
    out_dir: Path,
    *,
    mask_image_for_ref=None,  # callable(mask_ref) -> (PIL.Image L-mode, (l, t)) | None
) -> list[Path]:
    """Draw mask tint + bbox + track_id per frame. Pure rendering, no counting."""
    out_dir.mkdir(parents=True, exist_ok=True)
    by_frame: dict[int, list[tuple[Track, BBox, str | None]]] = {}
    for track in tracks:
        for frame in track.frames:
            by_frame.setdefault(frame.frame_index, []).append((track, frame.bbox, frame.mask_ref))
    out: list[Path] = []
    for idx, frame_path in enumerate(frame_paths):
        img = Image.open(frame_path).convert("RGB")
        draw = ImageDraw.Draw(img, "RGBA")
        for n, (track, bbox, mask_ref) in enumerate(by_frame.get(idx, [])):
            color = _COLORS[n % len(_COLORS)]
            if mask_ref and mask_image_for_ref is not None:
                resolved = mask_image_for_ref(mask_ref)
                if resolved is not None:
                    mask_img, (ml, mt) = resolved
                    tint = Image.new("RGB", mask_img.size, color)
                    img.paste(Image.blend(img.crop((ml, mt, ml + mask_img.width, mt + mask_img.height)),
                                          tint, 0.35),
                              (ml, mt), mask_img.point(lambda v: 110 if v else 0))
                    draw = ImageDraw.Draw(img, "RGBA")
            draw.rectangle([bbox.x1, bbox.y1, bbox.x2, bbox.y2], outline=color, width=3)
            draw.rectangle([bbox.x1, max(0, bbox.y1 - 16), bbox.x1 + 8 + 7 * len(track.track_id), bbox.y1],
                           fill=color)
            draw.text((bbox.x1 + 4, max(0, bbox.y1 - 15)), track.track_id, fill=(0, 0, 0))
        out_path = out_dir / f"overlay_{idx:04d}.png"
        img.save(out_path, format="PNG")
        out.append(out_path)
    return out


def encode_mp4(frame_paths: list[Path], out_path: Path, *, fps: float) -> Path:
    if not frame_paths:
        raise ValueError("no frames to encode")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pattern = str(frame_paths[0].parent / (frame_paths[0].name.rsplit("_", 1)[0] + "_%04d.png"))
    _run(["ffmpeg", "-y", "-v", "error", "-framerate", str(fps), "-i", pattern,
          "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out_path)])
    return out_path
