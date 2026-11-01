"""Policy simulation: edited text -> draft rules -> re-decide every past PO.

"Before" is the baseline policy's APPROVED rules recomputed through
domain.decision over the same facts as "after" (the in-memory draft).
Stored decisions are never read for the diff and never written; where a
stored decision disagrees with the recomputed baseline it is listed as
drift. Facts per line: video-backed lines take observed/damage from the
latest PerceptionResult; document-only lines take observed = GRN qty.
Lines with neither are skipped and counted. All arithmetic is Python.
"""

from __future__ import annotations

from app.core.errors import NotFoundError, ValidationError
from app.domain.decision import decide_delivery
from app.domain.enums import RuleStatus
from app.domain.money import format_inr
from app.domain.protocols import SimulationRepository
from app.domain.schemas.simulation import (
    DriftItem,
    EvidenceSourceTotals,
    HeldTotals,
    LineDecisionInput,
    LineDiff,
    PolicySimulationResult,
    PoVerdictDiff,
)
from app.services.line_facts import build_line_decision_input, row_to_compiled
from app.services.policy_compiler import PolicyCompilerService


class PolicySimulationService:
    def __init__(
        self,
        repository: SimulationRepository,
        compiler: PolicyCompilerService,
    ) -> None:
        self._repository = repository
        self._compiler = compiler

    async def simulate(
        self, *, policy_version: str, markdown: str, draft_version: str | None = None
    ) -> PolicySimulationResult:
        if not markdown.strip():
            raise ValidationError("Policy text is empty.", code="policy_empty")
        all_rows = self._repository.list_rules_for_version(policy_version)
        if not all_rows:
            raise NotFoundError(
                f"Policy version {policy_version!r} was not found.", code="policy_not_found"
            )
        baseline_rules = [
            rule
            for row in self._repository.list_rules_for_version(
                policy_version, status=RuleStatus.APPROVED.value
            )
            if (rule := row_to_compiled(row)) is not None
        ]

        draft = await self._compiler.compile_draft(markdown, policy_version=draft_version)
        draft_rules = [d.rule for d in draft.rules if not d.validation_errors]

        changed: list = []
        drift: list[DriftItem] = []
        unchanged = pos_evaluated = lines_evaluated = lines_skipped = 0
        held_before = held_after = 0
        by_source: dict[str, dict[str, int]] = {}

        for po in self._repository.list_purchase_orders():
            line_inputs: list[LineDecisionInput] = []
            for po_line in sorted(po.lines, key=lambda ln: ln.line_no):
                built = build_line_decision_input(self._repository, po_line)
                if built is None:
                    lines_skipped += 1
                    continue
                line_inputs.append(built)
            if not line_inputs:
                continue
            pos_evaluated += 1
            lines_evaluated += len(line_inputs)

            before = decide_delivery(line_inputs, baseline_rules)
            after = decide_delivery(line_inputs, draft_rules)
            held_before += before.held_paise
            held_after += after.held_paise
            for b_line, a_line in zip(before.lines, after.lines, strict=True):
                bucket = by_source.setdefault(
                    b_line.evidence_source, {"lines": 0, "before": 0, "after": 0}
                )
                bucket["lines"] += 1
                bucket["before"] += b_line.held_paise
                bucket["after"] += a_line.held_paise

            delivery = self._repository.get_delivery_for_po(po.id)
            stored = self._repository.get_latest_decision(po.id)
            if stored is not None and (
                stored.verdict != before.verdict.value
                or stored.amount_at_risk_paise != before.held_paise
            ):
                drift.append(
                    DriftItem(
                        po_id=po.id,
                        po_number=po.po_number,
                        delivery_id=delivery.id if delivery else None,
                        stored_decision_id=stored.id,
                        stored_verdict=stored.verdict,
                        stored_amount_at_risk_paise=stored.amount_at_risk_paise,
                        baseline_verdict=before.verdict,
                        baseline_held_paise=before.held_paise,
                    )
                )

            if before.verdict == after.verdict and before.held_paise == after.held_paise:
                unchanged += 1
                continue
            changed.append(
                PoVerdictDiff(
                    po_id=po.id,
                    po_number=po.po_number,
                    delivery_id=delivery.id if delivery else None,
                    before_verdict=before.verdict,
                    after_verdict=after.verdict,
                    before_held_paise=before.held_paise,
                    after_held_paise=after.held_paise,
                    held_delta_paise=after.held_paise - before.held_paise,
                    before_triggered_rule_ids=before.triggered_rule_ids,
                    after_triggered_rule_ids=after.triggered_rule_ids,
                    lines=[
                        LineDiff(
                            po_line_id=b.po_line_id,
                            evidence_source=b.evidence_source,
                            before_verdict=b.verdict,
                            after_verdict=a.verdict,
                            before_held_paise=b.held_paise,
                            after_held_paise=a.held_paise,
                        )
                        for b, a in zip(before.lines, after.lines, strict=True)
                    ],
                )
            )

        return PolicySimulationResult(
            policy_version=policy_version,
            draft_policy_version=draft.policy_version,
            draft_rules=draft.rules,
            draft_invalid=draft.invalid,
            draft_ambiguous=draft.ambiguous,
            draft_skipped_non_rule=draft.skipped_non_rule,
            draft_compiled=draft.compiled,
            draft_cache_hits=draft.cache_hits,
            draft_retries=draft.retries,
            baseline_approved_rules=len(baseline_rules),
            pos_evaluated=pos_evaluated,
            lines_evaluated=lines_evaluated,
            lines_skipped=lines_skipped,
            changed=changed,
            unchanged_count=unchanged,
            drift=drift,
            totals=HeldTotals(
                held_before_paise=held_before,
                held_after_paise=held_after,
                held_delta_paise=held_after - held_before,
                held_before_inr=format_inr(held_before),
                held_after_inr=format_inr(held_after),
            ),
            totals_by_evidence_source=[
                EvidenceSourceTotals(
                    evidence_source=source,
                    lines=v["lines"],
                    held_before_paise=v["before"],
                    held_after_paise=v["after"],
                    held_delta_paise=v["after"] - v["before"],
                )
                for source, v in sorted(by_source.items())
            ],
        )
