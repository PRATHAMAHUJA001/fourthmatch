"""Pure counting / evidence logic over SAM frame records. No I/O, no model calls."""
from __future__ import annotations

from collections.abc import Iterable

from app.domain.enums import EvidenceQuality
from app.domain.schemas.perception import PerceptionResult


def distinct_track_count(frame_object_ids: Iterable[Iterable[str]]) -> int:
    seen: set[str] = set()
    for frame in frame_object_ids:
        seen.update(frame)
    return len(seen)


def compute_max_visible(frame_object_ids: Iterable[Iterable[str]]) -> int:
    return max((len(set(frame)) for frame in frame_object_ids), default=0)


def assess_evidence_quality(
    *,
    track_count: int,
    max_visible: int,
    frames_with_tracks: int,
    total_frames: int,
) -> tuple[EvidenceQuality, list[str]]:
    reasons: list[str] = []
    if total_frames <= 0 or track_count == 0:
        return EvidenceQuality.NONE, ["no_tracks"]
    coverage = frames_with_tracks / total_frames
    if coverage < 0.5:
        reasons.append("low_frame_coverage")
    if max_visible == 0:
        reasons.append("nothing_visible")
    if reasons:
        return EvidenceQuality.WEAK, reasons
    return EvidenceQuality.STRONG, ["sufficient_coverage"]


def build_perception_result(
    *,
    delivery_id: int,
    sam_run_id: int,
    category: str,
    prompt: str,
    frame_object_ids: list[list[str]],
) -> PerceptionResult:
    frames = [list(frame) for frame in frame_object_ids]
    track_count = distinct_track_count(frames)
    max_visible = compute_max_visible(frames)
    frames_with_tracks = sum(1 for frame in frames if frame)
    quality, reasons = assess_evidence_quality(
        track_count=track_count,
        max_visible=max_visible,
        frames_with_tracks=frames_with_tracks,
        total_frames=len(frames),
    )
    return PerceptionResult(
        delivery_id=delivery_id,
        sam_run_id=sam_run_id,
        category=category,
        prompt=prompt,
        track_count=track_count,
        max_visible=max_visible,
        evidence_quality=quality,
        reasons=reasons,
    )
