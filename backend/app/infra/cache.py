"""SHA-256 keyed cache under storage/cache/. Re-running must never re-call SAM."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.core.errors import CacheError


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def cache_key_for(*parts: str) -> str:
    """Stable hex cache key from string parts (video hash, phrase, model...)."""
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


class Sha256Cache:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def key_for_bytes(self, data: bytes) -> str:
        return sha256_hex(data)

    def _path(self, key: str, suffix: str = ".bin") -> Path:
        if not key or any(c not in "0123456789abcdef" for c in key.lower()):
            raise CacheError(f"invalid cache key: {key!r}", code="cache_error")
        return self.root / f"{key}{suffix}"

    def get_bytes(self, key: str, suffix: str = ".bin") -> bytes | None:
        path = self._path(key, suffix)
        return path.read_bytes() if path.exists() else None

    def put_bytes(self, key: str, data: bytes, suffix: str = ".bin") -> Path:
        path = self._path(key, suffix)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        except OSError as exc:
            raise CacheError(f"cache write failed: {exc}", code="cache_error") from exc
        return path

    def get_json(self, key: str) -> Any | None:
        raw = self.get_bytes(key, suffix=".json")
        return json.loads(raw) if raw is not None else None

    def put_json(self, key: str, value: Any) -> Path:
        return self.put_bytes(key, json.dumps(value).encode(), suffix=".json")

    def get_or_put_bytes(self, data: bytes, suffix: str = ".bin") -> tuple[str, bytes, bool]:
        """Return (key, bytes, cache_hit)."""
        key = self.key_for_bytes(data)
        hit = self.get_bytes(key, suffix)
        if hit is not None:
            return key, hit, True
        self.put_bytes(key, data, suffix)
        return key, data, False
