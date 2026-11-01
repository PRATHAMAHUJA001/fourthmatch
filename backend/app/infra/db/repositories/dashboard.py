"""Read-only repository for dashboard aggregates. SELECTs only."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.domain.schemas.dashboard import JobSpan, ModelCallStat
from app.infra.db.models.decision import Decision
from app.infra.db.models.jobs import Job, ModelCall


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class SqlDashboardRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def decided_at_by_po(self) -> dict[int, datetime]:
        """Newest Decision timestamp per PO."""
        out: dict[int, datetime] = {}
        for po_id, created_at in (
            self._session.query(Decision.po_id, Decision.created_at).order_by(Decision.id).all()
        ):
            out[po_id] = _aware(created_at)
        return out

    def finished_job_spans(self) -> list[JobSpan]:
        rows = (
            self._session.query(Job.created_at, Job.finished_at)
            .filter(Job.status == "done", Job.finished_at.isnot(None))
            .all()
        )
        return [JobSpan(started_at=_aware(c), finished_at=_aware(f)) for c, f in rows if f is not None]

    def model_call_stats(self) -> list[ModelCallStat]:
        rows = self._session.query(
            ModelCall.model, ModelCall.purpose, ModelCall.latency_ms, ModelCall.cache_hit, ModelCall.status
        ).all()
        return [
            ModelCallStat(model=m, purpose=p, latency_ms=lat, cache_hit=bool(hit))
            for m, p, lat, hit, status in rows
            if status == "ok"
        ]
