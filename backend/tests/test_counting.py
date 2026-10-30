"""Pure counting tests over fixture JSON. No model calls (CLAUDE.md)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.domain.counting import apply_phrase_coverage, bbox_iou, count_line, generic_noun_for  # noqa: E402
from app.domain.schemas.config import CountingConfig  # noqa: E402
from app.domain.schemas.perception import BBox, Track  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text())


@pytest.mark.parametrize("name", ["split_track", "flicker", "reentering", "crossing"])
def test_counting_fixtures(name: str) -> None:
    fixture = _load(name)
    cfg = CountingConfig(**fixture.get("config", {}))
    tracks = [Track.model_validate(t) for t in fixture["tracks"]]
    result = count_line(tracks, cfg, total_frames=fixture["total_frames"])
    expected = fixture["expected"]
    assert result.observed_count == expected["observed_count"]
    assert result.max_visible == expected["max_visible"]
    assert len(result.merges) == expected["merge_count"]
    assert result.kept_track_ids == expected["kept_track_ids"]
    assert result.evidence_quality.value == expected["evidence_quality"]
    assert result.reasons == expected["reasons"]
    assert max(result.per_frame_counts) == expected["max_visible"]
    for merge in result.merges:  # every merge is recorded with its evidence
        assert merge.gap_frames >= 0
        assert merge.boundary_iou >= cfg.merge_min_iou


def test_no_tracks_is_insufficient_with_reason() -> None:
    result = count_line([], CountingConfig(), total_frames=10)
    assert result.observed_count == 0
    assert result.evidence_quality.value == "insufficient"
    assert result.reasons == ["no_tracks"]


def test_phrase_coverage_sacks() -> None:
    """scn4 reproduced: phrase 'white sack' sees 2, generic 'sack' sees 4."""
    fixture = _load("phrase_coverage_sacks")
    cfg = CountingConfig(**fixture.get("config", {}))
    phrase = count_line([Track.model_validate(t) for t in fixture["phrase_tracks"]], cfg,
                        total_frames=fixture["total_frames"])
    generic = count_line([Track.model_validate(t) for t in fixture["generic_tracks"]], cfg,
                         total_frames=fixture["total_frames"])
    assert phrase.observed_count == 2
    assert generic.observed_count == 4
    chosen = apply_phrase_coverage(phrase, generic)
    expected = fixture["expected"]
    assert chosen.observed_count == expected["observed_count"]
    assert chosen.max_visible == expected["max_visible"]
    assert chosen.evidence_quality.value == expected["evidence_quality"]
    assert chosen.reasons == expected["reasons"]
    assert {t.track_id for t in chosen.merged_tracks} == {"0", "1", "2", "3"}


def test_phrase_coverage_generic_below_phrase() -> None:
    fixture = _load("phrase_coverage_sacks")
    cfg = CountingConfig()
    phrase = count_line([Track.model_validate(t) for t in fixture["generic_tracks"]], cfg, total_frames=20)
    generic = count_line([Track.model_validate(t) for t in fixture["phrase_tracks"]], cfg, total_frames=20)
    chosen = apply_phrase_coverage(phrase, generic)
    assert chosen.observed_count == 4  # phrase count kept
    assert chosen.evidence_quality.value == "insufficient"
    assert chosen.reasons == ["phrase_coverage"]


def test_phrase_coverage_equal_and_absent() -> None:
    fixture = _load("phrase_coverage_sacks")
    cfg = CountingConfig()
    phrase = count_line([Track.model_validate(t) for t in fixture["phrase_tracks"]], cfg, total_frames=20)
    assert apply_phrase_coverage(phrase, phrase) is phrase
    assert apply_phrase_coverage(phrase, None) is phrase


def test_generic_noun_for_normalises_category() -> None:
    mapping = {"cartons": "box", "bagged material": "sack", "steel coils": "steel coil"}
    assert generic_noun_for("bagged_material", mapping) == "sack"
    assert generic_noun_for("Cartons", mapping) == "box"
    assert generic_noun_for("unknown", mapping) is None


def test_bbox_iou() -> None:
    a = BBox(x1=0, y1=0, x2=100, y2=100)
    assert bbox_iou(a, a) == 1.0
    assert bbox_iou(a, BBox(x1=200, y1=0, x2=300, y2=100)) == 0.0
