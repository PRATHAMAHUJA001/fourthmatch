"""Pure remark check: compare storekeeper claims with perception results.

Plain Python, no I/O, no model calls. Only "count" and "damage" claims can be
checked against the video; "other" claims (e.g. "the truck was late") are
ignored. The remark never changes a count, a damage flag or a verdict.
"""
from __future__ import annotations

from app.core.errors import ValidationError
from app.domain.schemas.remark import (
    ClaimVerdict,
    LineObservation,
    RemarkCheck,
    RemarkClaim,
    RemarkClaims,
    RemarkItem,
    RemarkStatus,
)


def _norm(value: str) -> str:
    return " ".join(value.replace("_", " ").lower().split())


def validate_claims(claims: RemarkClaims, valid_categories: list[str]) -> RemarkClaims:
    """Reject any category the model cites that is not a PO line category.

    Matching is case/underscore-insensitive; the canonical PO spelling is
    written back so later comparisons are exact.
    """
    canonical = {_norm(c): c for c in valid_categories}
    out: list[RemarkClaim] = []
    for claim in claims.claims:
        if claim.category is None:
            out.append(claim)
            continue
        match = canonical.get(_norm(claim.category))
        if match is None:
            raise ValidationError(
                f"remark claim cited unknown category {claim.category!r}; valid={sorted(canonical.values())}",
                code="model_output_invalid",
            )
        out.append(claim.model_copy(update={"category": match}))
    return RemarkClaims(claims=out)


def _select(claim: RemarkClaim, observations: list[LineObservation]) -> list[LineObservation] | None:
    """Lines a claim refers to: its category, or all lines when none is named."""
    if claim.category is None:
        return list(observations)
    picked = [o for o in observations if _norm(o.category) == _norm(claim.category)]
    return picked or None


def _check_count(claim: RemarkClaim, observations: list[LineObservation]) -> RemarkItem:
    lines = _select(claim, observations)
    unverifiable = RemarkItem(claim=claim, verdict=ClaimVerdict.UNVERIFIABLE)
    if claim.quantity is None or not lines:
        return unverifiable
    if claim.category is None and len(lines) != 1:
        return unverifiable  # which line is meant is unknown
    if any(not o.reliable or o.observed_count is None for o in lines):
        return unverifiable  # weak evidence can neither support nor refute
    observed = sum(o.observed_count or 0 for o in lines)
    verdict = ClaimVerdict.SUPPORTED if observed == claim.quantity else ClaimVerdict.NOT_SUPPORTED
    return RemarkItem(claim=claim, verdict=verdict, observed=observed)


def _check_damage(claim: RemarkClaim, observations: list[LineObservation]) -> RemarkItem:
    lines = _select(claim, observations)
    if not lines:
        return RemarkItem(claim=claim, verdict=ClaimVerdict.UNVERIFIABLE)
    damaged = sum(o.damaged_count for o in lines)
    if claim.quantity is None:
        supported = damaged >= 1  # "some boxes are damaged"
    elif claim.quantity == 0:
        supported = damaged == 0
    else:
        supported = damaged >= claim.quantity  # video confirms at least what was said
    verdict = ClaimVerdict.SUPPORTED if supported else ClaimVerdict.NOT_SUPPORTED
    return RemarkItem(claim=claim, verdict=verdict, observed=damaged)


def check_remark(claims: RemarkClaims, observations: list[LineObservation]) -> RemarkCheck:
    """Overall status: no checkable claim -> no_claim; any refuted -> not_supported;
    only unverifiable -> unverifiable; otherwise supported."""
    items: list[RemarkItem] = []
    for claim in claims.claims:
        if claim.kind == "count":
            items.append(_check_count(claim, observations))
        elif claim.kind == "damage":
            items.append(_check_damage(claim, observations))
    if not items:
        return RemarkCheck(status=RemarkStatus.NO_CLAIM, items=[])
    verdicts = {item.verdict for item in items}
    if ClaimVerdict.NOT_SUPPORTED in verdicts:
        status = RemarkStatus.NOT_SUPPORTED
    elif verdicts == {ClaimVerdict.UNVERIFIABLE}:
        status = RemarkStatus.UNVERIFIABLE
    else:
        status = RemarkStatus.SUPPORTED
    return RemarkCheck(status=status, items=items)
