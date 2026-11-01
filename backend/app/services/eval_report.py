"""Assemble data/eval_results.json from already-stored evidence. No model calls.

Callers (scripts/run_eval.py) gather typed inputs from the DB and data files;
every metric is computed by domain/metrics.py. Anything missing is reported in
``not_measured`` and left None, never filled with a guess.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Protocol

from app.domain.enums import Verdict
from app.domain.metrics import (
    count_summary,
    estimate_cost,
    latency_entries,
    verdict_score,
)
from app.domain.schemas.dashboard import ModelCallStat
from app.domain.schemas.eval import (
    CostRate,
    EvalImageLabel,
    EvalResults,
    ExpectedVerdict,
    ImageCountResult,
    ImageSection,
    ManifestLine,
    ModelUsage,
    ObservedLine,
    VerdictCaseResult,
    VerdictSection,
    VideoCountResult,
    VideoSection,
)


def _norm(category: str) -> str:
    return category.strip().lower().replace(" ", "_")


def build_video_section(manifest: Sequence[ManifestLine], observed: Sequence[ObservedLine]) -> VideoSection:
    by_key = {(o.scenario, _norm(o.category)): o for o in observed}
    rows: list[VideoCountResult] = []
    for line in manifest:
        obs = by_key.get((line.scenario, _norm(line.category)))
        count = obs.observed_count if obs else None
        damage = obs.flagged_damaged if obs else None
        rows.append(
            VideoCountResult(
                scenario=line.scenario,
                category=line.category,
                noun_phrase=obs.noun_phrase if obs else None,
                true_count=line.true_count,
                observed_count=count,
                true_damaged=line.true_damaged,
                flagged_damaged=damage,
                source=obs.source if obs else "none",
                count_correct=None if count is None else count == line.true_count,
                damage_correct=None if damage is None else damage == line.true_damaged,
            )
        )
    return VideoSection(
        rows=rows,
        count_summary=count_summary([(r.true_count, r.observed_count) for r in rows]),
        damage_summary=count_summary([(r.true_damaged, r.flagged_damaged) for r in rows]),
    )


def build_image_section(labels: Sequence[EvalImageLabel]) -> ImageSection:
    confirmed = [lb for lb in labels if lb.true_count is not None]
    rows = [
        ImageCountResult(
            id=lb.id, file=lb.file, phrase=lb.phrase, prompted_count=lb.prompted_count,
            sam_count=lb.sam_count, true_count=lb.true_count,
            correct=None if lb.sam_count is None else lb.sam_count == lb.true_count,
        )
        for lb in confirmed
        if lb.true_count is not None
    ]
    return ImageSection(
        images_total=len(labels),
        images_confirmed=len(confirmed),
        rows=rows,
        summary=count_summary([(r.true_count, r.sam_count) for r in rows]),
    )


def _cases(
    expected: Sequence[ExpectedVerdict], predicted: dict[str, Verdict | None]
) -> list[VerdictCaseResult]:
    out: list[VerdictCaseResult] = []
    for e in expected:
        if e.po_number not in predicted:
            continue
        # undecidable (no verdict) = routed to a human, as the dashboard does
        p = predicted[e.po_number] or Verdict.HUMAN_REVIEW
        out.append(VerdictCaseResult(po_number=e.po_number, scenario_id=e.scenario_id,
                                     expected=e.verdict, predicted=p, correct=p == e.verdict))
    return out


def build_verdict_section(
    expected: Sequence[ExpectedVerdict],
    served: dict[str, Verdict | None],
    served_unavailable_reason: str | None,
    agent: dict[str, Verdict],
) -> VerdictSection:
    section = VerdictSection()
    if served_unavailable_reason:
        section.served_reason = served_unavailable_reason
    else:
        section.served = verdict_score("served", _cases(expected, served))
    if agent:
        agent_cases = _cases(expected, dict(agent))
        section.agent = verdict_score("agent", agent_cases)
        if len(agent_cases) < len(expected):
            section.agent_reason = f"agent decision stored for {len(agent_cases)} of {len(expected)} cases"
    else:
        section.agent_reason = "no stored agent decision (run scripts/run_decisions.py with MODEL_API_KEY)"
    return section


def build_eval_results(
    *,
    manifest: Sequence[ManifestLine],
    observed: Sequence[ObservedLine],
    labels: Sequence[EvalImageLabel],
    expected: Sequence[ExpectedVerdict],
    served: dict[str, Verdict | None],
    served_unavailable_reason: str | None,
    agent: dict[str, Verdict],
    calls: Sequence[ModelCallStat],
    usage: Sequence[ModelUsage],
    deliveries_processed: int,
    rates: dict[str, CostRate],
    currency: str | None,
    now: datetime | None = None,
) -> EvalResults:
    videos = build_video_section(manifest, observed)
    images = build_image_section(labels)
    verdicts = build_verdict_section(expected, served, served_unavailable_reason, agent)
    latency = latency_entries(calls)
    cost = estimate_cost(usage, rates, deliveries_processed, currency)

    missing: list[str] = []
    unmeasured_videos = videos.count_summary.n - videos.count_summary.measured
    if unmeasured_videos:
        missing.append(
            f"video counts: {unmeasured_videos} of {videos.count_summary.n} manifest lines have no stored "
            "perception result (run scripts/eval_counts.py)"
        )
    if images.images_total == 0:
        missing.append("eval images: none generated (run scripts/gen_eval_images.py)")
    elif images.images_confirmed < images.images_total:
        missing.append(
            f"eval images: true_count confirmed for {images.images_confirmed} of {images.images_total} "
            "(run scripts/confirm_eval_images.py)"
        )
    if verdicts.served_reason:
        missing.append(f"served verdicts: {verdicts.served_reason}")
    if verdicts.agent_reason:
        missing.append(f"agent verdicts: {verdicts.agent_reason}")
    if not latency:
        missing.append("latency: no model_calls rows in the database")
    elif all(r.p50_ms is None for r in latency):
        missing.append("latency: only cache-hit calls logged, no live latency")
    if not cost.rates_configured:
        missing.append("cost: MODEL_COST_RATES / MODEL_COST_CURRENCY not configured (no prices are assumed)")
    elif cost.total_cost is None:
        missing.append("cost: a model with token usage has no configured rate")
    if cost.deliveries_processed == 0:
        missing.append("cost per delivery: no delivery has been processed by the pipeline in this database")

    return EvalResults(
        generated_at=now or datetime.now(UTC),
        videos=videos, images=images, verdicts=verdicts, latency=latency, cost=cost, not_measured=missing,
    )


class EvalSources(Protocol):
    """What the eval needs from storage (implemented by SqlEvaluationRepository)."""

    def observed_lines(self) -> list[ObservedLine]: ...

    def approved_rule_count(self) -> int: ...

    def agent_verdicts(self) -> dict[str, Verdict]: ...

    def model_call_stats(self) -> list[ModelCallStat]: ...

    def model_usage(self) -> list[ModelUsage]: ...

    def deliveries_processed(self) -> int: ...


def collect_eval_results(
    sources: EvalSources,
    *,
    manifest: Sequence[ManifestLine],
    exported_counts: Sequence[ObservedLine],
    labels: Sequence[EvalImageLabel],
    expected: Sequence[ExpectedVerdict],
    served: dict[str, Verdict | None],
    rates: dict[str, CostRate],
    currency: str | None,
    now: datetime | None = None,
) -> EvalResults:
    """Gather stored evidence and assemble the report. No model calls.

    Stored DB perception rows win over the exported data/eval_counts.json for
    the same (scenario, category). ``served`` is the CaseService recompute;
    it is only scored when approved rules exist, otherwise it is reported as
    not measured rather than as a wall of human_review misses.
    """
    merged = {(o.scenario, _norm(o.category)): o for o in exported_counts}
    merged.update({(o.scenario, _norm(o.category)): o for o in sources.observed_lines()})
    reason: str | None = None
    if sources.approved_rule_count() == 0:
        reason = ("no approved policy rules in this database (compile + approve rules first), "
                  "so the Python recompute has nothing to apply")
    if not served:
        reason = "no purchase orders in this database (run: cd backend && python -m app.seed)"
    return build_eval_results(
        manifest=manifest, observed=list(merged.values()), labels=labels, expected=expected,
        served=served, served_unavailable_reason=reason, agent=sources.agent_verdicts(),
        calls=sources.model_call_stats(), usage=sources.model_usage(),
        deliveries_processed=sources.deliveries_processed(), rates=rates, currency=currency, now=now,
    )
