"""Remark check logic (pure, fixture JSON) and claim validation. No model calls."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.errors import ValidationError
from app.domain.remark import check_remark, validate_claims
from app.domain.schemas.remark import (
    LineObservation,
    RemarkClaims,
    RemarkStatus,
)

FIX = json.loads((Path(__file__).parent / "fixtures" / "remark_cases.json").read_text())


def _claims(name: str) -> RemarkClaims:
    return RemarkClaims.model_validate(FIX[name])


def _obs(name: str) -> list[LineObservation]:
    return [LineObservation.model_validate(o) for o in FIX[name]]


def test_damage_claim_vs_zero_damaged_is_not_supported() -> None:
    check = check_remark(_claims("claims_damage_and_late"), _obs("obs_zero_damaged"))
    assert check.status is RemarkStatus.NOT_SUPPORTED
    assert len(check.items) == 1  # the "late" claim is not checkable
    assert check.items[0].verdict.value == "not_supported"
    assert check.items[0].observed == 0


def test_damage_claim_vs_two_damaged_is_supported() -> None:
    check = check_remark(_claims("claims_damage_and_late"), _obs("obs_two_damaged"))
    assert check.status is RemarkStatus.SUPPORTED
    assert check.items[0].observed == 2


def test_other_only_is_no_claim() -> None:
    check = check_remark(_claims("claims_late_only"), _obs("obs_two_damaged"))
    assert check.status is RemarkStatus.NO_CLAIM
    assert check.items == []


def test_count_claim_matches_observed() -> None:
    assert check_remark(_claims("claims_count"), _obs("obs_zero_damaged")).status is RemarkStatus.SUPPORTED
    wrong = RemarkClaims.model_validate(
        {"claims": [{"kind": "count", "category": "cartons", "quantity": 14, "text": "fourteen"}]}
    )
    assert check_remark(wrong, _obs("obs_zero_damaged")).status is RemarkStatus.NOT_SUPPORTED


def test_weak_evidence_is_unverifiable_never_refuted() -> None:
    check = check_remark(_claims("claims_count"), _obs("obs_weak_evidence"))
    assert check.status is RemarkStatus.UNVERIFIABLE
    assert check.items[0].observed is None


def test_count_claim_without_quantity_or_category_is_unverifiable() -> None:
    two_lines = [
        LineObservation(category="cartons", observed_count=4),
        LineObservation(category="steel coils", observed_count=2),
    ]
    claims = RemarkClaims.model_validate(
        {"claims": [{"kind": "count", "category": None, "quantity": 6, "text": "six items"}]}
    )
    assert check_remark(claims, two_lines).status is RemarkStatus.UNVERIFIABLE


def test_zero_damage_claim() -> None:
    claims = RemarkClaims.model_validate(
        {"claims": [{"kind": "damage", "category": None, "quantity": 0, "text": "nothing damaged"}]}
    )
    assert check_remark(claims, _obs("obs_zero_damaged")).status is RemarkStatus.SUPPORTED
    assert check_remark(claims, _obs("obs_two_damaged")).status is RemarkStatus.NOT_SUPPORTED


def test_validate_claims_normalises_and_rejects_unknown_category() -> None:
    loose = RemarkClaims.model_validate(
        {"claims": [{"kind": "damage", "category": "Steel_Coils", "quantity": 1, "text": "one coil"}]}
    )
    assert validate_claims(loose, ["steel coils"]).claims[0].category == "steel coils"
    with pytest.raises(ValidationError) as exc:
        validate_claims(_claims("claims_unknown_category"), ["cartons"])
    assert exc.value.code == "model_output_invalid"
