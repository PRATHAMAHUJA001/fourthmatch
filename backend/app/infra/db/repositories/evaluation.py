"""Read-only queries for scripts/run_eval.py. SELECTs only."""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.domain.enums import RuleStatus, Verdict
from app.domain.schemas.dashboard import ModelCallStat
from app.domain.schemas.eval import ModelUsage, ObservedLine
from app.infra.db.models.decision import Decision, Rule
from app.infra.db.models.jobs import ModelCall
from app.infra.db.models.perception import PerceptionResult, SamRun
from app.infra.db.models.purchasing import Delivery, PurchaseOrder
from app.infra.db.repositories.dashboard import SqlDashboardRepository


class SqlEvaluationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def observed_lines(self) -> list[ObservedLine]:
        """Newest stored perception result per (scenario, category)."""
        rows = (
            self._session.query(Delivery.scenario_id, PerceptionResult)
            .join(PerceptionResult, PerceptionResult.delivery_id == Delivery.id)
            .filter(Delivery.scenario_id.isnot(None))
            .order_by(PerceptionResult.id)
            .all()
        )
        latest: dict[tuple[str, str], ObservedLine] = {}
        for scenario_id, result in rows:
            latest[(str(scenario_id), result.category)] = ObservedLine(
                scenario=str(scenario_id),
                category=result.category,
                noun_phrase=result.noun_phrase,
                observed_count=result.observed_count,
                flagged_damaged=len(result.damaged_track_ids or []),
                source="db",
            )
        return list(latest.values())

    def approved_rule_count(self) -> int:
        return (
            self._session.query(func.count(Rule.id))
            .filter(Rule.status == RuleStatus.APPROVED.value, Rule.rule_id.isnot(None))
            .scalar()
            or 0
        )

    def agent_verdicts(self) -> dict[str, Verdict]:
        """po_number -> verdict of the newest stored decision, only if the agent (not the fallback) made it."""
        rows = (
            self._session.query(PurchaseOrder.po_number, Decision.source, Decision.verdict)
            .join(Decision, Decision.po_id == PurchaseOrder.id)
            .order_by(Decision.id)
            .all()
        )
        newest: dict[str, tuple[str, str]] = {po: (source, verdict) for po, source, verdict in rows}
        return {po: Verdict(v) for po, (source, v) in newest.items() if source == "agent"}

    def model_call_stats(self) -> list[ModelCallStat]:
        return SqlDashboardRepository(self._session).model_call_stats()

    def model_usage(self) -> list[ModelUsage]:
        """Token totals per model over successful live (non-cache) calls."""
        rows = (
            self._session.query(
                ModelCall.model,
                func.coalesce(func.sum(ModelCall.input_tokens), 0),
                func.coalesce(func.sum(ModelCall.output_tokens), 0),
            )
            .filter(ModelCall.status == "ok", ModelCall.cache_hit.is_(False))
            .group_by(ModelCall.model)
            .all()
        )
        return [ModelUsage(model=m, input_tokens=int(i), output_tokens=int(o)) for m, i, o in rows]

    def deliveries_processed(self) -> int:
        """Distinct deliveries the perception pipeline has run on."""
        return int(self._session.query(func.count(func.distinct(SamRun.delivery_id))).scalar() or 0)
