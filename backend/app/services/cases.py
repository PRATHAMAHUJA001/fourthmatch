"""Cases read model: every PO decided live, with its cited clauses.

Design, rationale, and file/test traceability: docs/CASES.md.

Verdicts are recomputed on read through domain.decision from APPROVED
compiled rules only (the newest policy version that has any) -- stored
Decision rows are never trusted here, matching the simulator's stance.
A PO with no evaluable line (no perception result and no GRN line) gets
``verdict=None``: not decidable yet, never a fabricated approve.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.core.errors import NotFoundError
from app.domain.agent_logic import discrepancy_types
from app.domain.decision import build_facts, decide_delivery
from app.domain.protocols import CaseRepository
from app.domain.schemas.cases import CaseDetail, CaseLineRead, CaseSummary, CitedRule
from app.domain.schemas.evidence import EvidencePackRead
from app.domain.schemas.policies import CompiledRule
from app.domain.schemas.simulation import LineDecisionInput
from app.services.case_facts import (
    approved_rules,
    decision_row_to_read,
    perception_read,
    tracks_for,
)
from app.services.line_facts import build_line_decision_input


class CaseService:
    def __init__(
        self,
        repository: CaseRepository,
        pack_lookup: Callable[[int], EvidencePackRead | None] | None = None,
    ) -> None:
        self._repository = repository
        # po_id -> latest evidence pack; injected so this module never imports
        # the evidence service (which itself depends on CaseService).
        self._pack_lookup = pack_lookup

    def list_cases(self) -> list[CaseSummary]:
        rules, policy_version = self._approved_rules()
        return [
            self._summarise(po, rules, policy_version)
            for po in self._repository.list_purchase_orders()
        ]

    def get_case(self, po_id: int) -> CaseDetail:
        po = self._repository.get_purchase_order(po_id)
        if po is None:
            raise NotFoundError(f"Purchase order {po_id} was not found.", code="po_not_found")
        rules, policy_version = self._approved_rules()
        summary, lines, verdict = self._build(po, rules, policy_version)
        delivery = self._repository.get_delivery_for_po(po.id)
        grn = self._repository.get_grn_for_po(po.id)
        invoice = self._repository.get_invoice_for_po(po.id)
        decision_row = self._repository.get_latest_decision(po.id)
        decision = decision_row_to_read(decision_row) if decision_row is not None else None
        if decision is not None:
            # Stale: the stored agent result no longer equals the live Python
            # recompute (e.g. policy changed). The served verdict is the recompute.
            decision.stale = (
                verdict is None
                or decision.verdict != verdict.verdict
                or decision.amount_held_paise != verdict.held_paise
            )
        return CaseDetail(
            **summary.model_dump(),
            delivery_id=delivery.id if delivery else None,
            grn_number=grn.grn_number if grn else None,
            invoice_number=invoice.invoice_number if invoice else None,
            triggered_rule_ids=verdict.triggered_rule_ids if verdict else [],
            signoff_roles=verdict.signoff_roles if verdict else [],
            lines=lines,
            video_url=(
                f"/api/deliveries/{delivery.id}/video"
                if delivery is not None and delivery.video_path else None
            ),
            decision=decision,
            invoice_total_paise=invoice.total_paise if invoice else None,
            evidence_pack=self._pack_lookup(po.id) if self._pack_lookup else None,
        )

    # -- internals ---------------------------------------------------------

    def _approved_rules(self) -> tuple[list[CompiledRule], str | None]:
        return approved_rules(self._repository)

    def _summarise(
        self, po: Any, rules: list[CompiledRule], policy_version: str | None
    ) -> CaseSummary:
        summary, _lines, _verdict = self._build(po, rules, policy_version)
        return summary

    def _build(self, po: Any, rules: list[CompiledRule], policy_version: str | None):
        po_lines = sorted(po.lines, key=lambda ln: ln.line_no)
        inputs: list[LineDecisionInput] = []
        input_by_line: dict[int, LineDecisionInput] = {}
        for po_line in po_lines:
            built = build_line_decision_input(self._repository, po_line)
            if built is not None:
                inputs.append(built)
                input_by_line[po_line.id] = built

        verdict = decide_delivery(inputs, rules) if inputs else None
        line_verdicts = {lv.po_line_id: lv for lv in verdict.lines} if verdict else {}
        rule_by_id = {r.rule_id: r for r in rules}

        lines: list[CaseLineRead] = []
        discrepancies: list[str] = []
        clauses: set[str] = set()
        for po_line in po_lines:
            line_input = input_by_line.get(po_line.id)
            line_verdict = line_verdicts.get(po_line.id)
            if line_input is not None:
                fired = line_verdict.triggered_rule_ids if line_verdict else []
                fired_fields = {rule_by_id[r].condition.field for r in fired if r in rule_by_id}
                for tag in discrepancy_types(line_input, fired_fields):
                    if tag not in discrepancies:
                        discrepancies.append(tag)
                clauses.update(rule_by_id[r].source_clause for r in fired if r in rule_by_id)
                perception_row = (
                    self._repository.get_perception_result(po_line.id)
                    if line_input.evidence_source == "video" else None
                )
                lines.append(
                    CaseLineRead(
                        po_line_id=po_line.id,
                        line_no=po_line.line_no,
                        sku=po_line.sku,
                        description=po_line.description,
                        category=po_line.category,
                        unit=po_line.unit,
                        po_qty=line_input.po_qty,
                        grn_qty=line_input.grn_qty,
                        invoiced_qty=line_input.invoiced_qty,
                        observed_count=line_input.observed_count,
                        damage_count=line_input.damage_count,
                        evidence_source=line_input.evidence_source,
                        evidence_quality=line_input.evidence_quality,
                        unit_price_paise=line_input.unit_price_paise,
                        po_unit_price_paise=(
                            line_input.po_unit_price_paise or line_input.unit_price_paise
                        ),
                        line_value_paise=line_input.line_value_paise,
                        variance_pct=build_facts(line_input).variance_pct,
                        verdict=line_verdict.verdict if line_verdict else None,
                        held_paise=line_verdict.held_paise if line_verdict else 0,
                        at_risk_paise=line_verdict.at_risk_paise if line_verdict else 0,
                        signoff_roles=line_verdict.signoff_roles if line_verdict else [],
                        perception=(
                            perception_read(perception_row, tracks_for(self._repository, perception_row))
                            if perception_row is not None else None
                        ),
                        cited_rules=[
                            CitedRule(
                                rule_id=rule.rule_id,
                                source_clause=rule.source_clause,
                                source_text=rule.source_text,
                                action=rule.action,
                            )
                            for rule_id in (line_verdict.triggered_rule_ids if line_verdict else [])
                            if (rule := rule_by_id.get(rule_id)) is not None
                        ],
                    )
                )
            else:
                invoice_line = self._repository.get_invoice_line(po_line.id)
                lines.append(
                    CaseLineRead(
                        po_line_id=po_line.id,
                        line_no=po_line.line_no,
                        sku=po_line.sku,
                        description=po_line.description,
                        category=po_line.category,
                        unit=po_line.unit,
                        po_qty=po_line.qty_ordered,
                        grn_qty=None,
                        invoiced_qty=invoice_line.qty_invoiced if invoice_line else 0,
                        observed_count=None,
                        damage_count=0,
                        evidence_source="none",
                        evidence_quality=None,
                        unit_price_paise=(
                            invoice_line.unit_price_paise if invoice_line else po_line.unit_price_paise
                        ),
                        po_unit_price_paise=po_line.unit_price_paise,
                        line_value_paise=(
                            invoice_line.qty_invoiced * invoice_line.unit_price_paise
                            if invoice_line
                            else 0
                        ),
                    )
                )

        vendor = self._repository.get_vendor(po.vendor_id)
        latest = self._repository.get_latest_decision(po.id)
        summary = CaseSummary(
            po_id=po.id,
            po_number=po.po_number,
            vendor_id=po.vendor_id,
            vendor_name=vendor.name if vendor else f"Vendor #{po.vendor_id}",
            scenario_id=po.scenario_id,
            status=po.status,
            order_date=po.order_date,
            expected_date=po.expected_date,
            total_paise=sum(ln.line_total_paise for ln in po_lines),
            verdict=verdict.verdict if verdict else None,
            held_paise=verdict.held_paise if verdict else 0,
            at_risk_paise=verdict.at_risk_paise if verdict else 0,
            policy_version=policy_version if verdict else None,
            lines_evaluated=len(inputs),
            lines_total=len(po_lines),
            discrepancy_types=discrepancies,
            clauses=sorted(clauses),
            evidence_source=_overall_source(inputs),
            decided_at=latest.created_at.isoformat() if latest is not None and latest.created_at else None,
        )
        return summary, lines, verdict


def _overall_source(inputs: list[LineDecisionInput]) -> str:
    sources = {i.evidence_source for i in inputs}
    if "video" in sources:
        return "video"
    return "document" if "document" in sources else "none"
