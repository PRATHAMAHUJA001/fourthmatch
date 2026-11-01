"""The current policy document: latest uploaded .md, else the bundled policy.

Uploaded markdown is kept verbatim under ``policies/`` in the storage root
(the compiler stores only compiled rules). The newest upload wins.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from app.core.errors import NotFoundError
from app.domain.policy_doc import parse_policy
from app.domain.schemas.dashboard import PolicyRead
from app.infra.storage import LocalFileStore

_DIR = "policies"


class PolicyDocService:
    def __init__(self, store: LocalFileStore, default_path: Path) -> None:
        self._store = store
        self._default_path = default_path

    def _uploads(self) -> list[Path]:
        folder = self._store.path_for(_DIR)
        return sorted(folder.glob("policy_*.md")) if folder.exists() else []

    def save_uploaded(self, markdown: str, version: str) -> Path:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        safe_version = "".join(ch if ch.isalnum() or ch in ".-" else "_" for ch in version) or "unknown"
        return self._store.put_bytes(f"{_DIR}/policy_{stamp}_{safe_version}.md", markdown.encode("utf-8"))

    def current(self) -> PolicyRead:
        uploads = self._uploads()
        if uploads:
            return parse_policy(uploads[-1].read_text(encoding="utf-8"), policy_id=len(uploads) + 1)
        if not self._default_path.exists():
            raise NotFoundError("No policy document is available.", code="policy_not_found")
        return parse_policy(self._default_path.read_text(encoding="utf-8"), policy_id=1)
