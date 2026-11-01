"""Audio helpers (ffmpeg). No model calls here."""
from __future__ import annotations

import subprocess
from pathlib import Path

from app.core.errors import ValidationError


def to_wav_16k_mono(src: Path, dst: Path) -> Path:
    """Convert webm/m4a/wav (anything ffmpeg can decode) to 16 kHz mono PCM WAV."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vn", "-ar", "16000", "-ac", "1",
             "-c:a", "pcm_s16le", str(dst)],
            check=True, capture_output=True, text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise ValidationError(
            f"remark audio could not be decoded: {exc.stderr.strip()[:200]}", code="remark_audio_invalid"
        ) from exc
    except FileNotFoundError as exc:
        raise ValidationError("ffmpeg is not installed", code="ffmpeg_missing") from exc
    return dst
