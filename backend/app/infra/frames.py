"""Evidence-frame collection for evidence packs. Implements domain FrameSource.

Prefers the tracked overlay frames the perception pipeline already rendered
into storage (storage/deliveries/<id>/overlay_line_*/overlay_*.png); when none
exist it grabs evenly spaced frames from the delivery video with ffmpeg.
Frames are re-encoded as bounded-width JPEGs so packs stay small. No model
calls, no counting.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import re
import subprocess
from pathlib import Path

from PIL import Image

from app.core.logging import get_logger
from app.domain.schemas.evidence import FrameCollection, FrameImage

logger = get_logger(__name__)

_OVERLAY_INDEX = re.compile(r"overlay_(\d+)\.png$")
MAX_FRAMES = 6
MAX_WIDTH = 960


def _to_jpeg(data: bytes) -> bytes:
    image = Image.open(io.BytesIO(data)).convert("RGB")
    if image.width > MAX_WIDTH:
        height = round(image.height * MAX_WIDTH / image.width)
        image = image.resize((MAX_WIDTH, height), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=85, optimize=True)
    return out.getvalue()


def evenly_spaced(total: int, count: int) -> list[int]:
    """``count`` indices spread across ``total`` items (centres of equal slices)."""
    if total <= 0 or count <= 0:
        return []
    count = min(count, total)
    return sorted({min(total - 1, int((i + 0.5) * total / count)) for i in range(count)})


class VideoFrameSource:
    def __init__(self, storage_root: Path, repo_root: Path, proxy_fps: float, *, count: int = 4) -> None:
        self._storage_root = storage_root
        self._repo_root = repo_root
        self._proxy_fps = proxy_fps
        self._count = max(3, min(count, MAX_FRAMES))

    # --------------------------------------------------------------- public
    def collect(self, *, delivery_id: int, video_path: str | None) -> FrameCollection:
        video = self._resolve_video(video_path)
        video_sha = self._sha256_file(video) if video else None
        overlay = self._overlay_frames(delivery_id)
        if overlay:
            return FrameCollection(frames=overlay, video_sha256=video_sha)
        if video is None:
            return FrameCollection(frames=[], video_sha256=None, note="Delivery video file not found; no frames.")
        try:
            frames = self._video_frames(video)
        except (subprocess.CalledProcessError, FileNotFoundError, OSError, ValueError) as exc:
            logger.warning("frame extraction failed: %s", type(exc).__name__)
            return FrameCollection(frames=[], video_sha256=video_sha, note="Frame extraction failed (ffmpeg unavailable).")
        return FrameCollection(frames=frames, video_sha256=video_sha)

    # -------------------------------------------------------------- helpers
    def _resolve_video(self, video_path: str | None) -> Path | None:
        if not video_path:
            return None
        candidate = Path(video_path)
        if candidate.is_absolute():
            return candidate if candidate.exists() else None
        for base in (self._repo_root, self._storage_root):
            alt = base / video_path
            if alt.exists():
                return alt
        return None

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _overlay_frames(self, delivery_id: int) -> list[FrameImage]:
        root = self._storage_root / "deliveries" / str(delivery_id)
        dirs = sorted(d for d in root.glob("overlay_line_*") if d.is_dir())
        out: list[FrameImage] = []
        if not dirs:
            return out
        per_dir = max(1, (self._count if len(dirs) == 1 else MAX_FRAMES) // len(dirs))
        for directory in dirs:
            files = sorted(directory.glob("overlay_*.png"))
            for pos in evenly_spaced(len(files), per_dir):
                path = files[pos]
                match = _OVERLAY_INDEX.search(path.name)
                frame_index = int(match.group(1)) if match else pos
                t_seconds = round(frame_index / self._proxy_fps, 2) if self._proxy_fps > 0 else None
                out.append(
                    FrameImage(
                        label=f"SAM track overlay ({directory.name.replace('overlay_line_', 'PO line ')})",
                        source="overlay",
                        frame_index=frame_index,
                        t_seconds=t_seconds,
                        jpeg=_to_jpeg(path.read_bytes()),
                    )
                )
        return out[:MAX_FRAMES]

    def _duration(self, video: Path) -> float:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(video)],
            check=True,
            capture_output=True,
            text=True,
        )
        duration = float(json.loads(result.stdout)["format"]["duration"])
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError("video has no duration")
        return duration

    def _video_frames(self, video: Path) -> list[FrameImage]:
        duration = self._duration(video)
        frames: list[FrameImage] = []
        for i in range(self._count):
            t = round(duration * (i + 0.5) / self._count, 2)
            result = subprocess.run(
                ["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(video), "-frames:v", "1",
                 "-f", "image2pipe", "-vcodec", "png", "-"],
                check=True,
                capture_output=True,
            )
            if not result.stdout:
                continue
            frames.append(
                FrameImage(
                    label="Dock video frame",
                    source="video_frame",
                    frame_index=None,
                    t_seconds=t,
                    jpeg=_to_jpeg(result.stdout),
                )
            )
        return frames
