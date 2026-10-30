"""Pure counting over SAM tracks. No I/O, no model calls, no arithmetic by LLM.

Pipeline: score/length filter -> merge re-entered objects -> count.
Thresholds arrive as CountingConfig (durations in seconds, converted with
proxy_fps) so changing fps never silently changes behaviour.
"""
from __future__ import annotations

from app.domain.enums import EvidenceQuality
from app.domain.schemas.config import CountingConfig
from app.domain.schemas.perception import BBox, CountResult, MergeRecord, Track


def bbox_iou(a: BBox, b: BBox) -> float:
    ix1, iy1 = max(a.x1, b.x1), max(a.y1, b.y1)
    ix2, iy2 = min(a.x2, b.x2), min(a.y2, b.y2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    area_a = max(0.0, a.x2 - a.x1) * max(0.0, a.y2 - a.y1)
    area_b = max(0.0, b.x2 - b.x1) * max(0.0, b.y2 - b.y1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def _passes_score(track: Track, cfg: CountingConfig) -> bool:
    mean = track.mean_score
    return mean is None or mean >= cfg.sam_score_min


def filter_tracks(
    tracks: list[Track], cfg: CountingConfig
) -> tuple[list[Track], list[Track], list[Track]]:
    """Split into (kept, short, low_score). Short = fewer than MIN_TRACK frames."""
    kept: list[Track] = []
    short: list[Track] = []
    low_score: list[Track] = []
    for track in tracks:
        track.frames.sort(key=lambda f: f.frame_index)
        if not _passes_score(track, cfg):
            low_score.append(track)
        elif len(track.frames) < cfg.min_track_frames:
            short.append(track)
        else:
            kept.append(track)
    return kept, short, low_score


def merge_reentered_tracks(tracks: list[Track], cfg: CountingConfig) -> tuple[list[Track], list[MergeRecord]]:
    """Join a track that leaves and re-enters: gap <= MERGE_MAX_GAP frames and
    boundary bbox IoU (last frame of earlier, first frame of later) >= MERGE_MIN_IOU.
    Tracks overlapping in time are never merged. Every merge is recorded."""
    ordered = sorted(tracks, key=lambda t: (t.first_frame if t.first_frame is not None else -1, t.track_id))
    merges: list[MergeRecord] = []
    changed = True
    while changed:
        changed = False
        for i, earlier in enumerate(ordered):
            if not earlier.frames:
                continue
            partner: tuple[int, Track, int, float] | None = None
            for j, later in enumerate(ordered):
                if i == j or not later.frames:
                    continue
                assert earlier.last_frame is not None and later.first_frame is not None
                gap = later.first_frame - earlier.last_frame - 1
                if gap < 0 or gap > cfg.merge_max_gap_frames:
                    continue
                iou = bbox_iou(earlier.frames[-1].bbox, later.frames[0].bbox)
                if iou >= cfg.merge_min_iou:
                    partner = (j, later, gap, iou)
                    break
            if partner is not None:
                j, later, gap, iou = partner
                merged = Track(
                    track_id=earlier.track_id,
                    phrase=earlier.phrase,
                    frames=sorted(earlier.frames + later.frames, key=lambda f: f.frame_index),
                )
                merges.append(
                    MergeRecord(
                        merged_track_ids=[earlier.track_id, later.track_id],
                        into_track_id=earlier.track_id,
                        gap_frames=gap,
                        boundary_iou=round(iou, 4),
                    )
                )
                ordered = [t for k, t in enumerate(ordered) if k not in (i, j)]
                ordered.append(merged)
                ordered.sort(key=lambda t: (t.first_frame if t.first_frame is not None else -1, t.track_id))
                changed = True
                break
    return ordered, merges


def generic_noun_for(category: str, mapping: dict[str, str]) -> str | None:
    """Category -> generic noun, matched normalised (case/underscore/space)."""
    key = category.strip().lower().replace("_", " ")
    for raw_key, noun in mapping.items():
        if raw_key.strip().lower().replace("_", " ") == key:
            return noun
    return None


def apply_phrase_coverage(phrase_count: CountResult, generic_count: CountResult | None) -> CountResult:
    """Phrase-coverage check (pure). The generic noun covers every unit of
    the category; the model's phrase may be too narrow (scn4: 'white sack'
    over white+brown sacks).

    - generic > phrase: count from the generic tracks, reason
      phrase_too_narrow; still reliable if every other check passed.
    - generic < phrase: keep the phrase count, insufficient + phrase_coverage.
    - equal / no generic run: phrase count unchanged.
    """
    if generic_count is None or generic_count.observed_count == phrase_count.observed_count:
        return phrase_count
    if generic_count.observed_count > phrase_count.observed_count:
        reasons = [*generic_count.reasons, "phrase_too_narrow"]
        quality = (
            EvidenceQuality.RELIABLE
            if generic_count.evidence_quality is EvidenceQuality.RELIABLE
            else EvidenceQuality.INSUFFICIENT
        )
        return generic_count.model_copy(update={"reasons": reasons, "evidence_quality": quality})
    reasons = [*phrase_count.reasons, "phrase_coverage"]
    return phrase_count.model_copy(update={"reasons": reasons, "evidence_quality": EvidenceQuality.INSUFFICIENT})


def per_frame_counts(tracks: list[Track], total_frames: int) -> list[int]:
    counts = [0] * total_frames
    for track in tracks:
        for idx in {f.frame_index for f in track.frames}:
            if 0 <= idx < total_frames:
                counts[idx] += 1
    return counts


def count_line(tracks: list[Track], cfg: CountingConfig, *, total_frames: int | None = None) -> CountResult:
    """Full pure count for one noun phrase. Evidence quality decided here."""
    raw = [t for t in tracks if t.frames]
    kept, short, _low = filter_tracks(raw, cfg)
    merged, merges = merge_reentered_tracks(kept, cfg)
    observed = len(merged)
    if total_frames is None:
        total_frames = max((t.last_frame or -1 for t in merged), default=-1) + 1
    frame_counts = per_frame_counts(merged, total_frames)
    max_visible = max(frame_counts, default=0)

    reasons: list[str] = []
    if observed == 0:
        reasons.append("no_tracks")
        quality = EvidenceQuality.INSUFFICIENT
    else:
        pre_filter_total = len(kept) + len(short)
        short_ratio = len(short) / pre_filter_total if pre_filter_total else 0.0
        merge_ratio = len(merges) / observed if observed else 0.0
        if short_ratio > cfg.max_short_track_ratio:
            reasons.append("short_track_ratio_high")
        if merge_ratio > cfg.max_merge_ratio:
            reasons.append("merge_ratio_high")
        if observed < max_visible:
            reasons.append("count_below_max_visible")
        quality = EvidenceQuality.INSUFFICIENT if reasons else EvidenceQuality.RELIABLE
    if quality is EvidenceQuality.RELIABLE:
        reasons = []
    return CountResult(
        observed_count=observed,
        max_visible=max_visible,
        per_frame_counts=frame_counts,
        kept_track_ids=[t.track_id for t in merged],
        merged_tracks=merged,
        merges=merges,
        evidence_quality=quality,
        reasons=reasons,
    )
