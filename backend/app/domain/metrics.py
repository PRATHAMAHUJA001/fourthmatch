"""Pure aggregation math for the dashboard endpoints. No I/O, no models.

Metrics, confusion matrix, percentiles, trend bucketing and per-vendor
roll-ups live here so they are unit-tested on fixture data. Every number the
dashboard shows is produced by these functions from stored rows.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime, timedelta

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
