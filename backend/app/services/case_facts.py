"""Shared case-facts assembly: approved rules, perception detail, per-delivery
CaseFacts for the decision agent, and stored Decision -> DecisionRead.

Read-only. All numbers come from the stored rows or domain.decision.
"""

from __future__ import annotations

from typing import Any

from app.core.errors import NotFoundError
from app.domain.protocols import CaseRepository
from app.domain.schemas.decision_agent import (
    AgentStep,
    CaseFacts,
    DecisionRead,
    LineCaseFacts,
    PerceptionRead,
    RecordDecisionLine,
    TrackRef,
)
from app.domain.schemas.policies import CompiledRule
from app.services.line_facts import build_line_decision_input, row_to_compiled


def approved_rules(repository: CaseRepository) -> tuple[list[CompiledRule], str | None]:
    """Valid approved compiled rules of the newest version that has any."""
    pairs: list[tuple[Any, CompiledRule]] = []
    for row in repository.list_approved_rules():
        rule = row_to_compiled(row)
        if rule is not None:
            pairs.append((row, rule))
    if not pairs:
        return [], None
    policy_version = max(pairs, key=lambda p: p[0].id)[0].policy_version
    return [rule for row, rule in pairs if row.policy_version == policy_version], policy_version


def tracks_for(repository: CaseRepository, perception: Any) -> list[TrackRef]:
    return [
        TrackRef(track_id=t.object_id, first_frame=t.first_frame, last_frame=t.last_frame)
        for t in repository.list_tracks(perception.sam_run_id)
    ]


def perception_read(perception: Any, tracks: list[TrackRef]) -> PerceptionRead:
    return PerceptionRead(
        noun_phrase=perception.noun_phrase,
        observed_count=perception.observed_count,
        max_visible=perception.max_visible,
        track_ids=[t.track_id for t in tracks],
        damaged_track_ids=[str(t) for t in (perception.damaged_track_ids or [])],
        reasons=[str(r) for r in (perception.reasons or [])],
        footage_needed=perception.footage_needed,
    )


def build_case_facts(repository: CaseRepository, delivery_id: int) -> CaseFacts:
    delivery = repository.get_delivery(delivery_id)
    if delivery is None:
        raise NotFoundError(f"Delivery {delivery_id} was not found.", code="delivery_not_found")
    po = repository.get_purchase_order(delivery.po_id)
    if po is None:
        raise NotFoundError(f"Purchase order {delivery.po_id} was not found.", code="po_not_found")
    rules, policy_version = approved_rules(repository)
    vendor = repository.get_vendor(po.vendor_id)
    grn = repository.get_grn_for_po(po.id)
    invoice = repository.get_invoice_for_po(po.id)
    lines: list[LineCaseFacts] = []
    for po_line in sorted(po.lines, key=lambda ln: ln.line_no):
        perception = repository.get_perception_result(po_line.id)
        tracks = tracks_for(repository, perception) if perception is not None else []
        lines.append(
            LineCaseFacts(
                po_line_id=po_line.id,
                line_no=po_line.line_no,
                sku=po_line.sku,
                description=po_line.description,
                category=po_line.category,
                unit=po_line.unit,
                facts=build_line_decision_input(repository, po_line),
                perception=perception_read(perception, tracks) if perception is not None else None,
                tracks=tracks,
            )
        )
    return CaseFacts(
        delivery_id=delivery.id,
        po_id=po.id,
        po_number=po.po_number,
        vendor_name=vendor.name if vendor else f"Vendor #{po.vendor_id}",
        grn_number=grn.grn_number if grn else None,
        invoice_id=invoice.id if invoice else None,
        invoice_number=invoice.invoice_number if invoice else None,
        invoice_total_paise=invoice.total_paise if invoice else None,
        policy_version=policy_version,
        lines=lines,
        rules=rules,
    )


def decision_row_to_read(row: Any) -> DecisionRead:
    return DecisionRead(
        verdict=row.verdict,
        amount_held_paise=row.amount_held_paise or 0,
        summary_en=row.summary_en or row.reason,
        recommended_action=row.recommended_action or "",
        model=row.model or "",
        trace=[AgentStep.model_validate(s) for s in (row.trace or [])],
        source=row.source or "agent",
        fallback_reasons=[str(r) for r in (row.fallback_reasons or [])],
        lines=[RecordDecisionLine.model_validate(ln) for ln in (row.lines or [])],
    )
