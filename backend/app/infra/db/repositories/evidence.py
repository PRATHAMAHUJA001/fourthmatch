"""Evidence repository: delivery lookup, latest decision, evidence_packs rows.

Implements domain.evidence.EvidenceRepository. Reads the Decision row with
getattr so optional agent fields (trace, summary, model...) are picked up
when the decision agent stores them, without coupling to its schema.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.domain.schemas.evidence import (
    DecisionSnapshot,
    DeliveryRef,
    ManifestEntry,
    NewPack,
    StoredPack,
    TraceStep,
)
from app.infra.db.models.decision import Decision, EvidencePack
from app.infra.db.models.purchasing import Delivery


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _compact(value: Any, limit: int = 160) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str, sort_keys=True)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _trace_steps(raw: Any) -> list[TraceStep]:
    steps: list[TraceStep] = []
    if not isinstance(raw, list):
        return steps
    for i, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            continue
        detail = {"args": item.get("args"), "result": item.get("result")}
        steps.append(
            TraceStep(seq=int(item.get("seq", i)), tool=str(item.get("tool", "step")), detail=_compact(detail))
        )
    return steps


def _stored(row: EvidencePack) -> StoredPack:
    return StoredPack(
        id=row.id,
        po_id=row.po_id,
        delivery_id=row.delivery_id,
        decision_id=row.decision_id,
        sha256=row.sha256 or "",
        verified=row.verified,
        created_at=_aware(row.created_at),
        pdf_path=row.pdf_path,
        json_path=row.json_path,
        manifest=[ManifestEntry.model_validate(m) for m in (row.manifest or [])],
    )


class SqlEvidenceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_delivery(self, delivery_id: int) -> DeliveryRef | None:
        row = self._session.get(Delivery, delivery_id)
        if row is None:
            return None
        return DeliveryRef(id=row.id, po_id=row.po_id, video_path=row.video_path)

    def get_latest_decision(self, po_id: int) -> DecisionSnapshot | None:
        row = (
            self._session.query(Decision)
            .filter(Decision.po_id == po_id)
            .order_by(Decision.id.desc())
            .first()
        )
        if row is None:
            return None
        summary = getattr(row, "summary_en", None)
        return DecisionSnapshot(
            id=row.id,
            verdict=row.verdict,
            reason=row.reason,
            decided_by=row.decided_by,
            created_at=_aware(row.created_at),
            model=getattr(row, "model", None),
            summary=summary if isinstance(summary, str) else None,
            recommended_action=getattr(row, "recommended_action", None),
            trace=_trace_steps(getattr(row, "trace", None)),
        )

    def add_pack(self, pack: NewPack) -> StoredPack:
        row = EvidencePack(
            po_id=pack.po_id,
            delivery_id=pack.delivery_id,
            decision_id=pack.decision_id,
            pdf_path=pack.pdf_path,
            json_path=pack.json_path,
            sha256=pack.sha256,
            verified=pack.verified,
            manifest=[m.model_dump(mode="json") for m in pack.manifest],
        )
        self._session.add(row)
        self._session.commit()
        return _stored(row)

    def latest_pack_for_po(self, po_id: int) -> StoredPack | None:
        row = (
            self._session.query(EvidencePack)
            .filter(EvidencePack.po_id == po_id, EvidencePack.sha256.isnot(None))
            .order_by(EvidencePack.id.desc())
            .first()
        )
        return _stored(row) if row else None

    def get_pack_by_sha(self, sha256: str) -> StoredPack | None:
        row = (
            self._session.query(EvidencePack)
            .filter(EvidencePack.sha256 == sha256)
            .order_by(EvidencePack.id.desc())
            .first()
        )
        return _stored(row) if row else None

    def set_verified(self, pack_id: int, verified: bool) -> None:
        row = self._session.get(EvidencePack, pack_id)
        if row is not None:
            row.verified = verified
            self._session.commit()
