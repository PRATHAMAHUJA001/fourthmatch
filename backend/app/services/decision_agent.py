"""FourthMatch payment-decision agent: tool-calling loop + Python guards.

The model (settings.DECISION_MODEL) calls deterministic tools and finishes
with record_decision. Python then validates that payload (schema, every
cited ID, tool coverage, amount recompute via domain.decision). A rejection
is fed back once; a second failure -- or any model/upstream error -- falls
back to the deterministic Python decision, marked source="fallback".
Pipeline state is persisted: the decisions row plus job_events
(reconciling, applying_policy, verdict). SSE only replays those rows.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import AppError
from app.core.logging import get_logger
from app.domain import agent_logic
from app.domain.protocols import ModelClient
from app.domain.schemas.decision_agent import (
    AgentStep,
    CaseFacts,
    DecisionRead,
    DecisionRecord,
    RecordDecisionPayload,
)
from app.infra.db.repositories.cases import SqlCaseRepository
from app.infra.db.repositories.decisions import SqlDecisionRepository
from app.services.agent_tools import RECORD_DECISION, CaseToolbox, tool_definitions
from app.services.case_facts import build_case_facts

logger = get_logger(__name__)

SYSTEM_PROMPT = (
    "You are FourthMatch's payment-decision agent. You decide whether a vendor invoice can be paid. "
    "Before deciding you MUST call compute_variance for every PO line and evaluate_rule for every "
    "applicable rule. You never do arithmetic yourself; use tool outputs only. If any line is "
    "evidence_quality insufficient, the verdict is human_review, never approve. Choose the most "
    "specific rule that fired. Every line in your decision cites rule_id, the policy clause number and "
    "the evidence (track IDs and frame index). Write summary_en for a finance manager in 2 plain "
    "sentences with the rupee amount. Finish by calling record_decision with: "
    "{verdict, amount_held_paise (integer paise), lines:[{po_line_id, po, grn, invoiced, observed, "
    "variance_pct, rule_id, clause, evidence:[]}], summary_en, recommended_action}"
)

MAX_INVALID_ATTEMPTS = 2  # first try + exactly one retry


def _user_message(text: str) -> dict[str, Any]:
    return {"type": "message", "role": "user", "content": [{"type": "input_text", "text": text}]}


class DecisionAgent:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        model_client: ModelClient,
        model: str,
        *,
        max_turns: int = 40,
        reasoning_effort: str = "high",
    ) -> None:
        self._factory = session_factory
        self._client = model_client
        self._model = model
        self._max_turns = max_turns
        self._effort = reasoning_effort

    async def run_standalone(self, delivery_id: int) -> DecisionRead:
        """(Re)run for an existing delivery under its own decision job."""
        return await self.run(delivery_id, job_id=None)

    async def run(self, delivery_id: int, *, job_id: str | None = None) -> DecisionRead:
        session = self._factory()
        try:
            facts = build_case_facts(SqlCaseRepository(session), delivery_id)
            repo = SqlDecisionRepository(session)
            standalone = job_id is None
            if job_id is None:
                job_id = repo.create_decision_job(delivery_id=delivery_id, po_id=facts.po_id)
            try:
                read = await self._decide(facts, session, repo, job_id)
            except Exception as exc:
                if standalone:
                    repo.finish_job(job_id, error_code=getattr(exc, "code", "internal_error"),
                                    message=str(exc)[:300])
                raise
            if standalone:
                repo.finish_job(job_id)
            return read
        finally:
            session.close()

    # ------------------------------------------------------------------ core
    async def _decide(
        self, facts: CaseFacts, session: Session, repo: SqlDecisionRepository, job_id: str
    ) -> DecisionRead:
        if not agent_logic.evaluable_lines(facts):
            raise AppError(
                "No line has video or GRN evidence yet; nothing to decide.",
                code="decision_no_evidence",
            )
        phase = _Phases(repo, job_id)
        phase.start_reconciling()
        trace: list[AgentStep] = []
        accepted, reasons = await self._loop(facts, session, trace, phase)
        phase.finish(have_rules=bool(facts.rules))

        source = "agent"
        if accepted is None:
            source = "fallback"
            accepted = agent_logic.fallback_payload(facts)
            logger.warning("decision agent fell back", extra={"extra_data": {
                "delivery_id": facts.delivery_id, "reasons": reasons}})
        expected = agent_logic.recompute(facts)
        rules_by_id = {r.rule_id: r for r in facts.rules}
        clauses = sorted({ln.clause for ln in accepted.lines if ln.clause}
                         | {rules_by_id[r].source_clause for r in expected.triggered_rule_ids if r in rules_by_id})
        variances = [ln.variance_pct for ln in accepted.lines if ln.variance_pct is not None]
        record = DecisionRecord(
            po_id=facts.po_id, delivery_id=facts.delivery_id, job_id=job_id,
            verdict=accepted.verdict, amount_held_paise=accepted.amount_held_paise,
            at_risk_paise=expected.at_risk_paise, summary_en=accepted.summary_en,
            recommended_action=accepted.recommended_action, model=self._model, source=source,
            fallback_reasons=reasons if source == "fallback" else [],
            trace=trace, lines=accepted.lines, clauses=clauses,
            variance_pct=max(variances) if variances else None,
        )
        repo.save_decision(record)
        repo.append_event(job_id, "verdict", f"verdict {record.verdict.value}",
                          {"verdict": record.verdict.value, "held_paise": record.amount_held_paise})
        return DecisionRead(
            verdict=record.verdict, amount_held_paise=record.amount_held_paise,
            summary_en=record.summary_en, recommended_action=record.recommended_action,
            model=record.model, trace=trace, source=source,
            fallback_reasons=record.fallback_reasons, stale=False, lines=record.lines,
        )

    async def _loop(
        self, facts: CaseFacts, session: Session, trace: list[AgentStep], phase: _Phases
    ) -> tuple[RecordDecisionPayload | None, list[str]]:
        toolbox = CaseToolbox(facts)
        tools = tool_definitions()
        history: list[dict[str, Any]] = [_user_message(
            f"Decide whether the invoice for delivery_id={facts.delivery_id} can be paid. "
            "Start with get_case. Amounts are integer paise."
        )]
        reasons: list[str] = []
        invalid = 0
        for _turn in range(self._max_turns):
            try:
                turn = await self._client.call_tool_turn(
                    purpose="decision_agent", model=self._model, instructions=SYSTEM_PROMPT,
                    input_items=history, tools=tools, session=session, reasoning_effort=self._effort,
                )
            except AppError as exc:
                reasons.append(f"model_error:{exc.code}")
                return None, reasons
            history.extend(turn.output_items)
            if not turn.calls:
                invalid += 1
                reasons.append("attempt_ended_without_record_decision")
                if invalid >= MAX_INVALID_ATTEMPTS:
                    return None, reasons
                history.append(_user_message(
                    "You must finish by calling record_decision after compute_variance and evaluate_rule."))
                continue
            for call in turn.calls:
                started = time.perf_counter()
                args, parse_error = _parse_args(call.arguments)
                accepted: RecordDecisionPayload | None = None
                if parse_error:
                    result: dict[str, Any] = {"error": parse_error}
                elif call.name == RECORD_DECISION:
                    result, accepted = _handle_record(args, facts, toolbox)
                else:
                    phase.on_tool(call.name)
                    result = toolbox.execute(call.name, args)
                trace.append(AgentStep(
                    seq=len(trace) + 1, tool=call.name, args=args, result=result,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                ))
                history.append({"type": "function_call_output", "call_id": call.call_id,
                                "output": json.dumps(result)})
                if accepted is not None:
                    return accepted, reasons
                if call.name == RECORD_DECISION:
                    invalid += 1
                    reasons.append(f"attempt {invalid} rejected: " + "; ".join(result.get("errors", [])))
                    if invalid >= MAX_INVALID_ATTEMPTS:
                        return None, reasons
        reasons.append("max_turns_exceeded")
        return None, reasons


def _parse_args(raw: str) -> tuple[dict[str, Any], str | None]:
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        return {}, f"arguments are not valid JSON: {exc.msg}"
    if not isinstance(value, dict):
        return {}, "arguments must be a JSON object"
    return value, None


def _handle_record(
    args: dict[str, Any], facts: CaseFacts, toolbox: CaseToolbox
) -> tuple[dict[str, Any], RecordDecisionPayload | None]:
    try:
        payload = RecordDecisionPayload.model_validate(args)
    except PydanticValidationError as exc:
        errors = [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()][:10]
        return {"accepted": False, "errors": errors}, None
    guard = agent_logic.validate_payload(payload, facts, toolbox.coverage)
    if guard.errors:
        return {"accepted": False, "errors": guard.errors}, None
    return {"accepted": True, "notes": guard.notes}, guard.payload


class _Phases:
    """Emits reconciling / applying_policy job_events from real progress."""

    def __init__(self, repo: SqlDecisionRepository, job_id: str) -> None:
        self._repo = repo
        self._job_id = job_id
        self._policy_started = False
        self._policy_finished = False

    def _emit(self, event_type: str, message: str) -> None:
        self._repo.append_event(self._job_id, event_type, message, {})

    def start_reconciling(self) -> None:
        self._emit("reconciling", "reconciling PO, GRN, invoice and video")

    def on_tool(self, name: str) -> None:
        if name in ("get_rules", "evaluate_rule") and not self._policy_started:
            self._emit("reconciling_finished", "reconciling finished")
            self._emit("applying_policy", "applying policy")
            self._policy_started = True

    def finish(self, *, have_rules: bool) -> None:
        if not self._policy_started:
            self._emit("reconciling_finished", "reconciling finished")
            self._emit("applying_policy", "applying policy")
            self._policy_started = True
        if not self._policy_finished:
            self._emit("applying_policy_finished", "applying policy finished")
            self._policy_finished = True


DecisionAgentFactory = Callable[[], DecisionAgent]
