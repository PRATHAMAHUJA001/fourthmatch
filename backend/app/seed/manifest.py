"""Load samples/scenarios/manifest.json — the only place scenario counts live.

The file shape is validated by Pydantic models whose aliases match the file
exactly (id, video, po, grn, invoice, true_count, true_damaged), extra="forbid".
Everything else about a scenario PO (vendor, SKU, unit, price) is a deterministic
catalog default in cases.py.
"""
from __future__ import annotations

from pathlib import Path

from app.domain.schemas.seed import ManifestFile, ManifestScenario, normalise_category

__all__ = ["load_manifest", "normalise_category"]


def load_manifest(path: Path, *, repo_root: Path) -> list[ManifestScenario]:
    """Return validated scenarios; validate ids are unique and videos exist."""
    doc = ManifestFile.model_validate_json(path.read_text())
    if not doc.scenarios:
        raise ValueError("manifest: 'scenarios' must be a non-empty list")
    seen: set[str] = set()
    for scn in doc.scenarios:
        if scn.scenario_id in seen:
            raise ValueError(f"manifest: duplicate scenario id {scn.scenario_id!r}")
        seen.add(scn.scenario_id)
        video_path = repo_root / "samples" / "scenarios" / scn.video
        if not video_path.exists():
            raise ValueError(f"manifest: video not found for {scn.scenario_id}: {video_path}")
    return doc.scenarios
