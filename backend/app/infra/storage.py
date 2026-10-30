"""Local file store. Paths are confined to the storage root."""
from __future__ import annotations

from pathlib import Path


class LocalFileStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, relative_path: str) -> Path:
        path = (self.root / relative_path).resolve()
        root = self.root.resolve()
        if root not in path.parents and path != root:
            raise ValueError(f"storage path escapes root: {relative_path!r}")
        return path

    def put_bytes(self, relative_path: str, data: bytes) -> Path:
        path = self._resolve(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def read_bytes(self, relative_path: str) -> bytes:
        return self._resolve(relative_path).read_bytes()

    def exists(self, relative_path: str) -> bool:
        return self._resolve(relative_path).exists()

    def path_for(self, relative_path: str) -> Path:
        return self._resolve(relative_path)
