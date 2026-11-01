"""Decision ORM: rules, decisions, evidence_packs."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.db.session import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Rule(Base):
    __tablename__ = "rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    clause: Mapped[str] = mapped_column(String(16), index=True)
    policy_version: Mapped[str] = mapped_column(String(16))
    category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    rule_type: Mapped[str] = mapped_column(String(48))
    threshold_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold_paise: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(32))
    description: Mapped[str] = mapped_column(Text)
    # Compiled-rule columns (policy compiler). Seed-template rows leave these
    # null; compiled rows fill them and start as pending_approval.
    rule_id: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True, index=True)
    goods_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    condition_field: Mapped[str | None] = mapped_column(String(48), nullable=True)
    condition_op: Mapped[str | None] = mapped_column(String(16), nullable=True)
    condition_value: Mapped[Any] = mapped_column(JSON, nullable=True)
    tolerance_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    signoff_role: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    ambiguity: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending_approval", index=True)
    validation_errors: Mapped[list[Any]] = mapped_column(JSON, default=list)
    conflict_with: Mapped[list[Any]] = mapped_column(JSON, default=list)


class Decision(Base):
    __tablename__ = "decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    po_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id"), index=True)
    delivery_id: Mapped[int | None] = mapped_column(ForeignKey("deliveries.id"), nullable=True)
    verdict: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(Text)
    policy_clauses: Mapped[list[Any]] = mapped_column(JSON, default=list)
    variance_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    amount_at_risk_paise: Mapped[int] = mapped_column(Integer, default=0)
    decided_by: Mapped[str] = mapped_column(String(80), default="agent")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    # Decision-agent columns (all nullable/defaulted: no migration needed).
    job_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="agent")  # agent | fallback
    model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    summary_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    amount_held_paise: Mapped[int] = mapped_column(Integer, default=0)
    trace: Mapped[list[Any]] = mapped_column(JSON, default=list)
    lines: Mapped[list[Any]] = mapped_column(JSON, default=list)
    fallback_reasons: Mapped[list[Any]] = mapped_column(JSON, default=list)


class EvidencePack(Base):
    __tablename__ = "evidence_packs"

    id: Mapped[int] = mapped_column(primary_key=True)
    po_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id"), index=True)
    decision_id: Mapped[int | None] = mapped_column(ForeignKey("decisions.id"), nullable=True)
    delivery_id: Mapped[int | None] = mapped_column(ForeignKey("deliveries.id"), nullable=True, index=True)
    pdf_path: Mapped[str | None] = mapped_column(String(300), nullable=True)
    json_path: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # sha256 = SHA-256 of the exact bytes of evidence_pack.json; manifest holds the
    # per-file hashes (pdf, debit note, frames) that verify re-checks.
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    manifest: Mapped[list[Any]] = mapped_column(JSON, default=list)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
