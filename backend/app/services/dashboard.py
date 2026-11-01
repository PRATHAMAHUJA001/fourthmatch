"""Dashboard read model: Dock KPIs, analytics, eval.

Everything is derived from what the cases service serves, plus stored rows
(decisions, jobs, model_calls) and the two committed data files. All math is
in domain/metrics.py. Nothing is invented: a day with no cases is a zero row,
a metric with no defined value is null.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError as PydanticValidationError

from app.core.errors import AppError
from app.domain.enums import Verdict
from app.domain.metrics import (
    VERDICT_LABELS,
    confusion_matrix,
    discrepancy_rate_pct,
    held_by_vendor,
    is_discrepancy,
    latency_rows,
    mean_seconds,
    ratio,
    trend_buckets,
    type_mix,
    vendor_risk,
    verdict_metrics,
)
from app.domain.schemas.cases import CaseDetail, CaseSummary
from app.domain.schemas.dashboard import (
    AnalyticsRead,
    Confusion,
    DockKpis,
    EvalCountRow,
    EvalRead,
    JobSpan,
    LatencyRow,
    ModelCallStat,
)
from app.domain.schemas.eval import EvalResults
from app.services.cases import CaseService
from app.services.eval_files import load_results


class DashboardRepository(Protocol):
    def decided_at_by_po(self) -> dict[int, datetime]: ...

    def finished_job_spans(self) -> list[JobSpan]: ...

    def model_call_stats(self) -> list[ModelCallStat]: ...


class DataFilesError(AppError):
    code = "data_file_invalid"
    status_code = 500


class DashboardService:
    def __init__(
        self,
        cases: CaseService,
        repository: DashboardRepository,
        *,
        ground_truth_path: Path,
        eval_counts_path: Path,
        eval_results_path: Path | None = None,
        today: Callable[[], date] = lambda: datetime.now(UTC).date(),
    ) -> None:
        self._cases = cases
        self._repo = repository
        self._ground_truth_path = ground_truth_path
        self._eval_counts_path = eval_counts_path
        self._eval_results_path = eval_results_path
        self._today = today

    # --------------------------------------------------------------- KPIs
    def dock_kpis(self) -> DockKpis:
        decided = [c for c in self._cases.list_cases() if c.verdict is not None]
        non_approved = sum(1 for c in decided if is_discrepancy(c))
        return DockKpis(
            held_today_paise=sum(c.held_paise for c in decided),
            deliveries_verified=sum(1 for c in decided if c.verdict is Verdict.APPROVE),
            deliveries_total=len(decided),
            discrepancy_rate_pct=discrepancy_rate_pct(non_approved, len(decided)),
            avg_time_to_verdict_s=mean_seconds(self._repo.finished_job_spans()),
        )

    # ---------------------------------------------------------- analytics
    def analytics(self) -> AnalyticsRead:
        summaries = self._cases.list_cases()
        decided = [c for c in summaries if c.verdict is not None]
        details: list[CaseDetail] = [self._cases.get_case(c.po_id) for c in decided]
        decided_at = self._repo.decided_at_by_po()
        events = [(self._case_day(c, decided_at), is_discrepancy(c)) for c in decided]
        return AnalyticsRead(
            held_by_vendor=held_by_vendor(decided),
            trend=trend_buckets(events, self._today()),
            type_mix=type_mix(details),
            vendor_risk=vendor_risk(decided),
        )

    @staticmethod
    def _case_day(case: CaseSummary, decided_at: dict[int, datetime]) -> date:
        """Decision date when a Decision row exists, else the PO's expected date."""
        stamp = decided_at.get(case.po_id)
        return stamp.date() if stamp is not None else case.expected_date

    # --------------------------------------------------------------- eval
    def evaluation(self) -> EvalRead:
        truth = self._load_ground_truth()
        served = {c.po_number: c.verdict for c in self._cases.list_cases()}
        pairs: list[tuple[str, str]] = []
        for po_number, correct in truth.items():
            predicted = served.get(po_number) or Verdict.HUMAN_REVIEW  # undecidable = routed to a human
            pairs.append((correct, predicted.value))
        matrix = confusion_matrix(pairs)
        counts = self._load_counts()
        results = self._load_results()
        latency = latency_rows(self._repo.model_call_stats())
        if not latency and results is not None:  # no live calls here (e.g. a demo container): use the measured run
            latency = [
                LatencyRow(model=r.model, role=r.role, calls=r.calls, p50_ms=r.p50_ms, p95_ms=r.p95_ms)
                for r in results.latency
            ]
        return EvalRead(
            verdict_metrics=verdict_metrics(matrix),
            confusion=Confusion(labels=list(VERDICT_LABELS), matrix=matrix),
            counts=counts,
            latency=latency,
            results=results,
            cases_total=len(pairs),
            verdict_accuracy=ratio(sum(1 for t, p in pairs if t == p), len(pairs)),
            count_accuracy=ratio(sum(1 for c in counts if c.result == "PASS"), len(counts)),
        )

    def _load_ground_truth(self) -> dict[str, str]:
        raw = self._read_json(self._ground_truth_path)
        cases = raw.get("scenarios_and_discrepancies") if isinstance(raw, dict) else None
        if not isinstance(cases, list):
            raise DataFilesError(f"{self._ground_truth_path.name} has no scenarios_and_discrepancies list.")
        out: dict[str, str] = {}
        for case in cases:
            try:
                out[str(case["po_number"])] = Verdict(case["correct_verdict"]).value
            except (KeyError, ValueError, TypeError) as exc:
                raise DataFilesError(f"{self._ground_truth_path.name}: bad case entry ({exc}).") from exc
        return out

    def _load_results(self) -> EvalResults | None:
        if self._eval_results_path is None:
            return None
        try:
            return load_results(self._eval_results_path)
        except (OSError, PydanticValidationError) as exc:
            raise DataFilesError(f"{self._eval_results_path.name} is unreadable or failed validation.") from exc

    def _load_counts(self) -> list[EvalCountRow]:
        if not self._eval_counts_path.exists():
            return []
        raw = self._read_json(self._eval_counts_path)
        if not isinstance(raw, list):
            raise DataFilesError(f"{self._eval_counts_path.name} must be a JSON list.")
        try:
            return [EvalCountRow.model_validate(row) for row in raw]
        except PydanticValidationError as exc:
            raise DataFilesError(f"{self._eval_counts_path.name}: row failed validation.") from exc

    @staticmethod
    def _read_json(path: Path) -> object:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DataFilesError(f"Cannot read {path.name}.") from exc
