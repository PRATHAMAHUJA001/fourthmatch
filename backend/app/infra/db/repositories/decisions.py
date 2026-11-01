"""Writes for the decision agent. Implements domain DecisionRepository."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.domain.enums import JobKind, JobStatus
from app.domain.schemas.decision_agent import DecisionRecord
from app.infra.db.models.decision import Decision
from app.infra.db.models.jobs import Job, append_job_event


class SqlDecisionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save_decision(self, record: DecisionRecord) -> int:
        row = Decision(
            po_id=record.po_id,
            delivery_id=record.delivery_id,
            job_id=record.job_id,
            verdict=record.verdict.value,
            reason=record.summary_en,
            policy_clauses=record.clauses,
            variance_pct=record.variance_pct,
            amount_at_risk_paise=record.at_risk_paise,
            decided_by="agent" if record.source == "agent" else "fallback",
            source=record.source,
            model=record.model,
            summary_en=record.summary_en,
            recommended_action=record.recommended_action,
            amount_held_paise=record.amount_held_paise,
            trace=[s.model_dump(mode="json") for s in record.trace],
            lines=[ln.model_dump(mode="json") for ln in record.lines],
            fallback_reasons=list(record.fallback_reasons),
        )
        self._session.add(row)
        self._session.commit()
        return row.id

    def append_event(
        self, job_id: str, event_type: str, message: str, payload: dict[str, Any] | None = None
    ) -> None:
        append_job_event(self._session, job_id, event_type, message, payload or {})
        self._session.commit()

    def create_decision_job(self, *, delivery_id: int, po_id: int) -> str:
        job = Job(
            kind=JobKind.DECISION.value,
            status=JobStatus.QUEUED.value,
            delivery_id=delivery_id,
            po_id=po_id,
            started_at=datetime.now(UTC),
        )
        self._session.add(job)
        self._session.flush()
        append_job_event(self._session, job.id, JobStatus.QUEUED.value, "decision queued",
                         {"delivery_id": delivery_id, "po_id": po_id})
        self._session.commit()
        return job.id

    def finish_job(
        self, job_id: str, *, error_code: str | None = None, message: str | None = None
    ) -> None:
        job = self._session.get(Job, job_id)
        if job is None:
            return
        job.finished_at = datetime.now(UTC)
        if error_code:
            job.status = JobStatus.FAILED.value
            job.error_code = error_code
            job.error_message = message
            append_job_event(self._session, job_id, JobStatus.FAILED.value, message or "failed",
                             {"error_code": error_code})
        else:
            job.status = JobStatus.DONE.value
            job.progress_pct = 100
            append_job_event(self._session, job_id, JobStatus.DONE.value, "done", {})
        self._session.commit()
