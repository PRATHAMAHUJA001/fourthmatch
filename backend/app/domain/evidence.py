"""Evidence-pack logic: document assembly, hashing, ports. Pure Python.

Ports (Protocols) are implemented in infra and injected by api/deps.
Everything numeric is computed here from the decided case; nothing is
taken from a model.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Protocol, runtime_checkable

from app.domain.enums import Verdict
from app.domain.money import format_inr
from app.domain.schemas.cases import CaseDetail, CaseLineRead
from app.domain.schemas.dashboard import PolicyRead
from app.domain.schemas.evidence import (
    AgentTraceSummary,
    CaseSection,
    CitedClause,
    DebitLine,
    DebitNoteSection,
    DecisionSnapshot,
    DeliveryRef,
    EvidenceFrame,
    EvidencePackDocument,
    FourMatchRow,
    FrameCollection,
    NewPack,
    PackModels,
    StoredPack,
)

PDF_NAME = "evidence_pack.pdf"
JSON_NAME = "evidence_pack.json"
DEBIT_NAME = "debit_note.pdf"


# ------------------------------------------------------------------- ports
@runtime_checkable
class FileStore(Protocol):
    def put_bytes(self, relative_path: str, data: bytes) -> Path: ...

    def read_bytes(self, relative_path: str) -> bytes: ...

    def exists(self, relative_path: str) -> bool: ...


class FrameSource(Protocol):
    def collect(self, *, delivery_id: int, video_path: str | None) -> FrameCollection: ...


class PackRenderer(Protocol):
    def render_pack(self, doc: EvidencePackDocument, frames: dict[str, bytes], pack_sha256: str) -> bytes: ...

    def render_debit_note(self, doc: EvidencePackDocument, pack_sha256: str) -> bytes: ...


class EvidenceRepository(Protocol):
    def get_delivery(self, delivery_id: int) -> DeliveryRef | None: ...

    def get_latest_decision(self, po_id: int) -> DecisionSnapshot | None: ...

    def add_pack(self, pack: NewPack) -> StoredPack: ...

    def latest_pack_for_po(self, po_id: int) -> StoredPack | None: ...

    def get_pack_by_sha(self, sha256: str) -> StoredPack | None: ...

    def set_verified(self, pack_id: int, verified: bool) -> None: ...


# ----------------------------------------------------------------- hashing
def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def short_hash(sha256: str, length: int = 12) -> str:
    return sha256[:length]


def canonical_json(doc: EvidencePackDocument) -> bytes:
    """Deterministic JSON bytes of the document: sorted keys, 2-space indent, UTF-8."""
    payload = doc.model_dump(mode="json")
    return (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


# ------------------------------------------------------------- assembly
def build_four_match(case: CaseDetail) -> list[FourMatchRow]:
    rows: list[FourMatchRow] = []
    for line in case.lines:
        contradicts = (
            line.evidence_source == "video"
            and line.observed_count is not None
            and line.grn_qty is not None
            and line.observed_count != line.grn_qty
        )
        rows.append(
            FourMatchRow(
                line_no=line.line_no,
                sku=line.sku,
                description=line.description,
                unit=line.unit,
                po_qty=line.po_qty,
                grn_qty=line.grn_qty,
                invoiced_qty=line.invoiced_qty,
                vision_count=line.observed_count if line.evidence_source == "video" else None,
                vision_source=line.evidence_source,
                evidence_quality=line.evidence_quality,
                damage_count=line.damage_count,
                unit_price_paise=line.unit_price_paise,
                unit_price_display=format_inr(line.unit_price_paise, decimals=True),
                variance_pct=line.variance_pct,
                verdict=line.verdict,
                held_paise=line.held_paise,
                held_display=format_inr(line.held_paise),
                contradicts_grn=contradicts,
            )
        )
    return rows


def build_cited_clauses(case: CaseDetail, policy: PolicyRead | None) -> list[CitedClause]:
    """One entry per cited rule. Clause text is the policy document's verbatim
    clause when it exists there, else the compiled rule's source text."""
    policy_text = {c.clause_id: c.text for c in policy.clauses} if policy else {}
    ordered: dict[str, CitedClause] = {}
    for line in case.lines:
        for rule in line.cited_rules:
            existing = ordered.get(rule.rule_id)
            if existing is not None:
                if line.line_no not in existing.line_nos:
                    existing.line_nos.append(line.line_no)
                continue
            from_policy = policy_text.get(rule.source_clause)
            ordered[rule.rule_id] = CitedClause(
                rule_id=rule.rule_id,
                clause_id=rule.source_clause,
                clause_text=from_policy if from_policy else rule.source_text,
                clause_source="policy_document" if from_policy else "compiled_rule",
                action=rule.action,
                line_nos=[line.line_no],
            )
    return list(ordered.values())


def _line_reason(line: CaseLineRead) -> str:
    facts = [f"PO {line.po_qty}", f"invoiced {line.invoiced_qty}"]
    if line.grn_qty is not None:
        facts.append(f"GRN {line.grn_qty}")
    if line.observed_count is not None:
        facts.append(f"{'video' if line.evidence_source == 'video' else 'recorded'} {line.observed_count}")
    if line.damage_count:
        facts.append(f"damaged {line.damage_count}")
    return "Disputed value withheld; " + ", ".join(facts) + f" ({line.unit})."


def build_debit_note(case: CaseDetail, generated_at: datetime) -> DebitNoteSection | None:
    """Debit note for partial_pay cases: one line per line with withheld value."""
    if case.verdict is not Verdict.PARTIAL_PAY:
        return None
    lines: list[DebitLine] = []
    for line in case.lines:
        if line.held_paise <= 0:
            continue
        qty = (
            line.held_paise // line.unit_price_paise
            if line.unit_price_paise > 0 and line.held_paise % line.unit_price_paise == 0
            else None
        )
        lines.append(
            DebitLine(
                line_no=line.line_no,
                description=line.description,
                unit=line.unit,
                qty=qty,
                unit_price_paise=line.unit_price_paise,
                amount_paise=line.held_paise,
                amount_display=format_inr(line.held_paise, decimals=True),
                reason=_line_reason(line),
                clauses=sorted({r.source_clause for r in line.cited_rules}),
            )
        )
    if not lines:
        return None
    total = sum(ln.amount_paise for ln in lines)
    return DebitNoteSection(
        number=f"DN/26-27/{case.po_id:04d}",
        issue_date=generated_at.date(),
        vendor_name=case.vendor_name,
        po_number=case.po_number,
        invoice_number=case.invoice_number,
        lines=lines,
        total_paise=total,
        total_display=format_inr(total, decimals=True),
    )


def build_trace_summary(decision: DecisionSnapshot | None) -> AgentTraceSummary:
    if decision is None:
        return AgentTraceSummary(
            recorded=False,
            note=(
                "No agent decision is stored for this case. The verdict shown was computed "
                "by the deterministic rules engine from approved compiled rules."
            ),
        )
    return AgentTraceSummary(
        recorded=True,
        decision_id=decision.id,
        verdict=decision.verdict,
        reason=decision.reason,
        decided_by=decision.decided_by,
        decided_at=decision.created_at,
        model=decision.model,
        summary=decision.summary,
        recommended_action=decision.recommended_action,
        steps=decision.trace,
    )


def build_pack_document(
    *,
    case: CaseDetail,
    delivery_id: int,
    policy: PolicyRead | None,
    decision: DecisionSnapshot | None,
    models: PackModels,
    frames: list[EvidenceFrame],
    frames_note: str,
    video_sha256: str | None,
    generated_at: datetime,
) -> EvidencePackDocument:
    if case.verdict is None:
        raise ValueError("case has no verdict; evidence packs are built only for decided cases")
    return EvidencePackDocument(
        generated_at=generated_at,
        case=CaseSection(
            po_id=case.po_id,
            po_number=case.po_number,
            vendor_name=case.vendor_name,
            scenario_id=case.scenario_id,
            status=case.status,
            order_date=case.order_date,
            expected_date=case.expected_date,
            delivery_id=delivery_id,
            grn_number=case.grn_number,
            invoice_number=case.invoice_number,
            policy_version=case.policy_version,
            lines_evaluated=case.lines_evaluated,
            lines_total=case.lines_total,
            po_total_paise=case.total_paise,
            po_total_display=format_inr(case.total_paise),
        ),
        verdict=case.verdict,
        amount_held_paise=case.held_paise,
        amount_held_display=format_inr(case.held_paise),
        at_risk_paise=case.at_risk_paise,
        at_risk_display=format_inr(case.at_risk_paise),
        signoff_roles=case.signoff_roles,
        four_match=build_four_match(case),
        cited_clauses=build_cited_clauses(case, policy),
        frames=frames,
        frames_note=frames_note,
        video_sha256=video_sha256,
        agent_trace=build_trace_summary(decision),
        models=models,
        debit_note=build_debit_note(case, generated_at),
    )


def safe_filename_part(value: str) -> str:
    """PO numbers contain '/', which is unsafe in a filename."""
    return "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in value).strip("-")
