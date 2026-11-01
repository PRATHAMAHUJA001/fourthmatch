"""Pure aggregation math for the dashboard endpoints. No I/O, no models.

Metrics, confusion matrix, percentiles, trend bucketing and per-vendor
roll-ups live here so they are unit-tested on fixture data. Every number the
dashboard shows is produced by these functions from stored rows.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from app.domain.enums import Verdict
from app.domain.schemas.cases import CaseDetail, CaseSummary
from app.domain.schemas.dashboard import (
    HeldByVendor,
    JobSpan,
    LatencyRow,
    ModelCallStat,
    TrendPoint,
    TypeMix,
    VendorRisk,
    VerdictMetric,
)
from app.domain.schemas.eval import (
    ClassMetric,
    ConfusionTable,
    CostRate,
    CostSection,
    CountSummary,
    LatencyEntry,
    ModelCost,
    ModelUsage,
    VerdictCaseResult,
    VerdictScore,
)

VERDICT_LABELS: list[Verdict] = [Verdict.APPROVE, Verdict.PARTIAL_PAY, Verdict.HOLD, Verdict.HUMAN_REVIEW]

TREND_DAYS = 30

# Policy clause -> discrepancy type vocabulary used by the dashboard.
CLAUSE_DISCREPANCY: dict[str, str] = {
    "4.2": "short_shipment_beyond_tolerance",
    "5.1": "invoice_price_above_po",
    "5.2": "invoice_qty_exceeds_po",
    "5.3": "duplicate_invoice_number",
    "6.1": "damaged_units_invoiced",
}
VIDEO_CONTRADICTS_GRN = "grn_contradicted_by_video"
INSUFFICIENT_EVIDENCE = "insufficient_evidence"
OTHER_CLAUSE = "other_policy_clause"


# --------------------------------------------------------------------- KPIs
def discrepancy_rate_pct(non_approved: int, total: int) -> float:
    """Share of decided cases that are not a clean approve, 1 decimal."""
    if total <= 0:
        return 0.0
    return round(non_approved / total * 100, 1)


def mean_seconds(spans: Iterable[JobSpan]) -> float | None:
    """Mean upload-to-done time in seconds; None when no finished job exists."""
    durations = [
        (_aware(s.finished_at) - _aware(s.started_at)).total_seconds() for s in spans
    ]
    durations = [d for d in durations if d >= 0]
    if not durations:
        return None
    return round(sum(durations) / len(durations), 1)


def _aware(value: datetime) -> datetime:
    """SQLite hands back naive datetimes for timezone-aware columns: treat as UTC."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


# ------------------------------------------------------------- eval metrics
def confusion_matrix(
    pairs: Sequence[tuple[str, str]], labels: Sequence[Verdict] = VERDICT_LABELS
) -> list[list[int]]:
    """Rows = ground truth, columns = predicted. Unknown labels raise."""
    index = {label.value: i for i, label in enumerate(labels)}
    matrix = [[0] * len(labels) for _ in labels]
    for truth, predicted in pairs:
        if truth not in index or predicted not in index:
            raise ValueError(f"unknown verdict label in pair ({truth!r}, {predicted!r})")
        matrix[index[truth]][index[predicted]] += 1
    return matrix


def verdict_metrics(
    matrix: list[list[int]], labels: Sequence[Verdict] = VERDICT_LABELS
) -> list[VerdictMetric]:
    """Per-label precision/recall/F1; None where the ratio is undefined."""
    out: list[VerdictMetric] = []
    for i, label in enumerate(labels):
        tp = matrix[i][i]
        predicted = sum(row[i] for row in matrix)
        support = sum(matrix[i])
        precision = tp / predicted if predicted else None
        recall = tp / support if support else None
        f1: float | None = None
        if precision is not None and recall is not None and precision + recall > 0:
            f1 = 2 * precision * recall / (precision + recall)
        out.append(VerdictMetric(label=label, precision=precision, recall=recall, f1=f1, support=support))
    return out


def ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def percentile(values: Sequence[float], pct: float) -> float | None:
    """Linear-interpolation percentile (numpy 'linear'); None for no data."""
    if not values:
        return None
    if not 0 <= pct <= 100:
        raise ValueError("pct must be within 0..100")
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (len(ordered) - 1) * pct / 100
    lower = math.floor(rank)
    upper = math.ceil(rank)
    fraction = rank - lower
    return float(ordered[lower] + (ordered[upper] - ordered[lower]) * fraction)


def latency_rows(calls: Iterable[ModelCallStat]) -> list[LatencyRow]:
    """Per (model, role) call count with p50/p95 over measured live calls.

    ``calls`` counts every logged call. Percentiles use only calls that have a
    latency and were not served from cache (a cache hit measures the disk, not
    the model); a group with none of those reports null, never zero.
    """
    grouped: dict[tuple[str, str], list[ModelCallStat]] = {}
    for call in calls:
        grouped.setdefault((call.model, call.purpose), []).append(call)
    rows: list[LatencyRow] = []
    for (model, purpose), group in sorted(grouped.items()):
        live = [float(c.latency_ms) for c in group if c.latency_ms is not None and not c.cache_hit]
        p50 = percentile(live, 50)
        p95 = percentile(live, 95)
        rows.append(
            LatencyRow(
                model=model,
                role=purpose,
                calls=len(group),
                p50_ms=round(p50, 1) if p50 is not None else None,
                p95_ms=round(p95, 1) if p95 is not None else None,
            )
        )
    return rows


# --------------------------------------------------------------- analytics
def discrepancy_types(case: CaseDetail) -> list[str]:
    """Discrepancy types of one decided case, derived from its evidence.

    Clause-based types come from the rules the case actually cited; the
    video-vs-GRN contradiction is detected from the counts. A human_review
    case with no cited clause is 'insufficient_evidence'. Clean cases: [].
    """
    found: list[str] = []
    for line in case.lines:
        if (
            line.evidence_source == "video"
            and line.observed_count is not None
            and line.grn_qty is not None
            and line.observed_count < line.grn_qty
        ):
            found.append(VIDEO_CONTRADICTS_GRN)
            break
    clauses = {rule.source_clause for line in case.lines for rule in line.cited_rules}
    for clause in sorted(clauses):
        found.append(CLAUSE_DISCREPANCY.get(clause, OTHER_CLAUSE))
    if not found and case.verdict is Verdict.HUMAN_REVIEW:
        found.append(INSUFFICIENT_EVIDENCE)
    return list(dict.fromkeys(found))


def type_mix(cases: Iterable[CaseDetail]) -> list[TypeMix]:
    counter: Counter[str] = Counter()
    for case in cases:
        counter.update(discrepancy_types(case))
    return [TypeMix(type=t, count=n) for t, n in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))]


def is_discrepancy(case: CaseSummary) -> bool:
    return case.verdict is not None and case.verdict is not Verdict.APPROVE


def held_by_vendor(cases: Iterable[CaseSummary]) -> list[HeldByVendor]:
    totals: dict[str, list[int]] = {}
    for case in cases:
        if case.verdict is None:
            continue
        entry = totals.setdefault(case.vendor_name, [0, 0])
        entry[0] += case.held_paise
        entry[1] += 1
    rows = [HeldByVendor(vendor_name=v, held_paise=t[0], cases=t[1]) for v, t in totals.items()]
    return sorted(rows, key=lambda r: (-r.held_paise, r.vendor_name))


def risk_score(cases: int, discrepancies: int) -> int:
    """Percentage of a vendor's decided cases that were discrepancies."""
    return round(discrepancies / cases * 100) if cases else 0


def vendor_risk(cases: Iterable[CaseSummary]) -> list[VendorRisk]:
    totals: dict[str, list[int]] = {}
    for case in cases:
        if case.verdict is None:
            continue
        entry = totals.setdefault(case.vendor_name, [0, 0, 0])
        entry[0] += 1
        entry[1] += 1 if is_discrepancy(case) else 0
        entry[2] += case.held_paise
    rows = [
        VendorRisk(
            vendor_name=v, cases=t[0], discrepancies=t[1], held_paise=t[2], risk_score=risk_score(t[0], t[1])
        )
        for v, t in totals.items()
    ]
    return sorted(rows, key=lambda r: (-r.risk_score, -r.held_paise, r.vendor_name))


def trend_buckets(
    events: Iterable[tuple[date, bool]], today: date, days: int = TREND_DAYS
) -> list[TrendPoint]:
    """Daily buckets for the last ``days`` days ending ``today`` (inclusive).

    ``events`` are (day, is_discrepancy) per decided case. Days without data
    are zero rows, never interpolated or invented; events outside the window
    are ignored.
    """
    start = today - timedelta(days=days - 1)
    deliveries: Counter[date] = Counter()
    discrepancies: Counter[date] = Counter()
    for day, flagged in events:
        if start <= day <= today:
            deliveries[day] += 1
            if flagged:
                discrepancies[day] += 1
    return [
        TrendPoint(
            date=start + timedelta(days=i),
            deliveries=deliveries[start + timedelta(days=i)],
            discrepancies=discrepancies[start + timedelta(days=i)],
        )
        for i in range(days)
    ]


# ------------------------------------------------------------ eval report
def count_summary(pairs: Sequence[tuple[int, int | None]]) -> CountSummary:
    """Exact-match count accuracy over (true, observed) pairs.

    ``observed`` None means not measured: it is excluded from accuracy and MAE
    (never counted as wrong or as zero) but still counted in ``n``.
    """
    measured = [(t, o) for t, o in pairs if o is not None]
    correct = sum(1 for t, o in measured if t == o)
    return CountSummary(
        n=len(pairs),
        measured=len(measured),
        correct=correct,
        accuracy=correct / len(measured) if measured else None,
        mean_abs_error=sum(abs(t - o) for t, o in measured) / len(measured) if measured else None,
    )


def macro_average(metrics: Sequence[VerdictMetric]) -> tuple[float | None, float | None, float | None]:
    """Macro precision/recall/F1 over labels that have ground-truth support.

    Labels with support 0 are skipped (nothing to recall). For a supported
    label whose precision is undefined (the system never predicted it) the
    undefined value counts as 0.0, the usual zero-division convention.
    """
    supported = [m for m in metrics if m.support > 0]
    if not supported:
        return None, None, None
    n = len(supported)
    return (
        sum(m.precision or 0.0 for m in supported) / n,
        sum(m.recall or 0.0 for m in supported) / n,
        sum(m.f1 or 0.0 for m in supported) / n,
    )


def verdict_score(
    source: Literal["served", "agent"],
    cases: Sequence[VerdictCaseResult],
    labels: Sequence[Verdict] = VERDICT_LABELS,
) -> VerdictScore:
    """Accuracy, per-class P/R/F1, macro averages and confusion for one verdict source."""
    matrix = confusion_matrix([(c.expected.value, c.predicted.value) for c in cases], labels)
    per_class = verdict_metrics(matrix, labels)
    macro_p, macro_r, macro_f = macro_average(per_class)
    correct = sum(1 for c in cases if c.correct)
    return VerdictScore(
        source=source,
        cases_total=len(cases),
        cases_correct=correct,
        accuracy=correct / len(cases) if cases else None,
        per_class=[
            ClassMetric(label=m.label, precision=m.precision, recall=m.recall, f1=m.f1, support=m.support)
            for m in per_class
        ],
        macro_precision=macro_p,
        macro_recall=macro_r,
        macro_f1=macro_f,
        confusion=ConfusionTable(labels=list(labels), matrix=matrix),
        cases=list(cases),
    )


def latency_entries(calls: Iterable[ModelCallStat]) -> list[LatencyEntry]:
    """Per (model, purpose) latency with the number of live (non-cache) calls."""
    stats = list(calls)
    live: Counter[tuple[str, str]] = Counter(
        (c.model, c.purpose) for c in stats if c.latency_ms is not None and not c.cache_hit
    )
    return [
        LatencyEntry(
            model=r.model, role=r.role, calls=r.calls, live_calls=live[(r.model, r.role)],
            p50_ms=r.p50_ms, p95_ms=r.p95_ms,
        )
        for r in latency_rows(stats)
    ]


def parse_cost_rates(raw: str | None) -> dict[str, CostRate]:
    """Parse MODEL_COST_RATES: JSON {"<model id>": {"input_per_1m": x, "output_per_1m": y}}.

    Empty/unset returns {} (cost is then reported as not measured). Malformed
    input raises ValueError rather than silently pricing at zero.
    """
    if raw is None or not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"MODEL_COST_RATES is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("MODEL_COST_RATES must be a JSON object keyed by model id")
    return {str(model): CostRate.model_validate(rate) for model, rate in data.items()}


def estimate_cost(
    usage: Sequence[ModelUsage],
    rates: dict[str, CostRate],
    deliveries_processed: int,
    currency: str | None,
) -> CostSection:
    """Token cost per model and per delivery. Never guesses a price.

    A model that used tokens but has no configured rate has cost None, and then
    the total (and per-delivery) is None too, so a partial price never passes
    as the whole cost. Covers token-billed usage only.
    """
    per_model: list[ModelCost] = []
    for u in sorted(usage, key=lambda x: x.model):
        rate = rates.get(u.model)
        if rate is not None:
            cost: float | None = u.input_tokens / 1_000_000 * rate.input_per_1m + u.output_tokens / 1_000_000 * rate.output_per_1m
        elif u.input_tokens + u.output_tokens == 0:
            cost = 0.0
        else:
            cost = None
        per_model.append(ModelCost(model=u.model, input_tokens=u.input_tokens, output_tokens=u.output_tokens, cost=cost))
    priced = bool(per_model) and all(m.cost is not None for m in per_model) and currency is not None
    total = sum(m.cost or 0.0 for m in per_model) if priced else None
    return CostSection(
        rates_configured=bool(rates) and currency is not None,
        currency=currency if priced else None,
        deliveries_processed=deliveries_processed,
        total_input_tokens=sum(u.input_tokens for u in usage),
        total_output_tokens=sum(u.output_tokens for u in usage),
        total_cost=total,
        cost_per_delivery=total / deliveries_processed if total is not None and deliveries_processed > 0 else None,
        per_model=per_model,
    )
