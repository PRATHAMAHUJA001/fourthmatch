"""Shared per-line facts: ORM rows -> LineDecisionInput + rule conversion.

Used by both policy simulation and the cases read model, so a line's
observed/damage/invoiced facts are assembled in exactly one place.
Video-backed lines take observed/damage from the latest PerceptionResult;
document-only lines take observed = GRN qty. Lines with neither return
None: no observed quantity exists. All arithmetic is Python.
"""

from __future__ import annotations

from typing import Any, Protocol

from app.domain.rules import validate_rule
from app.domain.schemas.policies import CompiledRule, RuleCondition
from app.domain.schemas.simulation import LineDecisionInput


class LineFactsRepository(Protocol):
    """The read-only lookups line-fact assembly needs."""

    def get_grn_line(self, po_line_id: int) -> Any | None: ...

    def get_invoice_line(self, po_line_id: int) -> Any | None: ...

    def get_perception_result(self, po_line_id: int) -> Any | None: ...

    def is_duplicate_invoice(
        self, *, vendor_id: int, invoice_number: str, exclude_invoice_id: int
    ) -> bool: ...


def row_to_compiled(row: object) -> CompiledRule | None:
    """Stored rule row -> CompiledRule, or None if not a valid compiled rule."""
    if not getattr(row, "condition_field", None) or not getattr(row, "rule_id", None):
        return None
    if list(getattr(row, "validation_errors", None) or []):
        return None
    rule = CompiledRule(
        rule_id=row.rule_id,  # type: ignore[attr-defined]
        goods_category=row.goods_category or row.category or "",  # type: ignore[attr-defined]
        condition=RuleCondition(
            field=row.condition_field,  # type: ignore[attr-defined]
            op=row.condition_op or "",  # type: ignore[attr-defined]
            value=row.condition_value,  # type: ignore[attr-defined]
        ),
        action=row.action,  # type: ignore[attr-defined]
        signoff_role=row.signoff_role,  # type: ignore[attr-defined]
        source_clause=row.clause,  # type: ignore[attr-defined]
        source_text=row.source_text or "",  # type: ignore[attr-defined]
        ambiguity=row.ambiguity,  # type: ignore[attr-defined]
    )
    return None if validate_rule(rule) else rule


def build_line_decision_input(
    repository: LineFactsRepository, po_line: Any
) -> LineDecisionInput | None:
    perception = repository.get_perception_result(po_line.id)
    grn_line = repository.get_grn_line(po_line.id)
    invoice_line = repository.get_invoice_line(po_line.id)
    invoiced_qty = invoice_line.qty_invoiced if invoice_line else po_line.qty_ordered
    unit_price_paise = (
        invoice_line.unit_price_paise if invoice_line else po_line.unit_price_paise
    )
    grn_qty = grn_line.qty_received if grn_line else None
    duplicate = False
    if invoice_line is not None and invoice_line.invoice is not None:
        duplicate = repository.is_duplicate_invoice(
            vendor_id=invoice_line.invoice.vendor_id,
            invoice_number=invoice_line.invoice.invoice_number,
            exclude_invoice_id=invoice_line.invoice_id,
        )
    if perception is not None:
        return LineDecisionInput(
            po_line_id=po_line.id,
            goods_category=po_line.category,
            evidence_source="video",
            evidence_quality=perception.evidence_quality,
            observed_count=perception.observed_count,
            invoiced_qty=invoiced_qty,
            po_qty=po_line.qty_ordered,
            grn_qty=grn_qty,
            damage_count=len(perception.damaged_track_ids or []),
            unit_price_paise=unit_price_paise,
            po_unit_price_paise=po_line.unit_price_paise,
            duplicate_invoice=duplicate,
            line_value_paise=invoiced_qty * unit_price_paise,
        )
    if grn_line is not None:
        return LineDecisionInput(
            po_line_id=po_line.id,
            goods_category=po_line.category,
            evidence_source="document",
            evidence_quality=None,
            observed_count=grn_line.qty_received,
            invoiced_qty=invoiced_qty,
            po_qty=po_line.qty_ordered,
            grn_qty=grn_qty,
            damage_count=grn_line.qty_damaged,
            unit_price_paise=unit_price_paise,
            po_unit_price_paise=po_line.unit_price_paise,
            duplicate_invoice=duplicate,
            line_value_paise=invoiced_qty * unit_price_paise,
        )
    return None  # neither video nor GRN: no observed quantity exists
