"""Eval contracts: synthetic eval-image labels and the data/eval_results.json file.

Every number in EvalResults is computed in Python (domain/metrics.py). A value
that was not measured is None (or an empty list) and is named in
``not_measured``; it is never zero and never invented.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.domain.enums import Verdict


class EvalImageLabel(BaseModel):
    """One generated still in data/eval_images/labels.json.

    ``prompted_count`` is what the image prompt asked for (not ground truth: the
    image model does not obey counts exactly). ``true_count`` stays None until a
    human confirms it by looking at the picture.
    """

    id: str
    file: str
    prompt: str
    phrase: str
    prompted_count: int = Field(ge=0)
    sam_count: int | None = Field(default=None, ge=0)
    true_count: int | None = Field(default=None, ge=0)
    synthetic: Literal[True] = True


# ------------------------------------------------------------------ results
class CountSummary(BaseModel):
    n: int  # rows considered
    measured: int  # rows with an observed count
    correct: int  # observed == true
    accuracy: float | None = None  # correct / measured; None when nothing measured
    mean_abs_error: float | None = None


class VideoCountResult(BaseModel):
    scenario: str
    category: str
    noun_phrase: str | None = None
    true_count: int
    observed_count: int | None = None
    true_damaged: int
    flagged_damaged: int | None = None
    source: Literal["db", "eval_counts", "none"]
    count_correct: bool | None = None
    damage_correct: bool | None = None


class ImageCountResult(BaseModel):
    id: str
    file: str
    phrase: str
    prompted_count: int
    sam_count: int | None = None
    true_count: int
    correct: bool | None = None
    synthetic: Literal[True] = True


class VideoSection(BaseModel):
    rows: list[VideoCountResult] = Field(default_factory=list)
    count_summary: CountSummary
    damage_summary: CountSummary


class ImageSection(BaseModel):
    synthetic: Literal[True] = True
    images_total: int
    images_confirmed: int  # have a human-confirmed true_count
    rows: list[ImageCountResult] = Field(default_factory=list)  # confirmed only
    summary: CountSummary


class ClassMetric(BaseModel):
    label: Verdict
    precision: float | None = None
    recall: float | None = None
    f1: float | None = None
    support: int


class VerdictCaseResult(BaseModel):
    po_number: str
    scenario_id: str | None = None
    expected: Verdict
    predicted: Verdict
    correct: bool


class ConfusionTable(BaseModel):
    labels: list[Verdict]
    matrix: list[list[int]]  # rows = ground truth, columns = predicted


class VerdictScore(BaseModel):
    """Scores of one verdict source (served Python recompute, or stored agent)."""

    source: Literal["served", "agent"]
    cases_total: int
    cases_correct: int
    accuracy: float | None = None
    per_class: list[ClassMetric]
    macro_precision: float | None = None
    macro_recall: float | None = None
    macro_f1: float | None = None
    confusion: ConfusionTable
    cases: list[VerdictCaseResult]


class VerdictSection(BaseModel):
    served: VerdictScore | None = None
    served_reason: str | None = None  # why served is None
    agent: VerdictScore | None = None
    agent_reason: str | None = None  # why agent is None


class LatencyEntry(BaseModel):
    model: str
    role: str
    calls: int
    live_calls: int  # calls that actually reached the model (not cache hits)
    p50_ms: float | None = None
    p95_ms: float | None = None


class CostRate(BaseModel):
    """Price of one model per 1M tokens, in ``currency`` of the config. Supplied by the operator."""

    input_per_1m: float = Field(ge=0)
    output_per_1m: float = Field(ge=0)


class ModelUsage(BaseModel):
    """Token totals of one model, summed from model_calls (live calls only)."""

    model: str
    input_tokens: int = 0
    output_tokens: int = 0


class ModelCost(BaseModel):
    model: str
    input_tokens: int
    output_tokens: int
    cost: float | None = None


class CostSection(BaseModel):
    rates_configured: bool
    currency: str | None = None
    deliveries_processed: int
    total_input_tokens: int
    total_output_tokens: int
    total_cost: float | None = None
    cost_per_delivery: float | None = None
    per_model: list[ModelCost] = Field(default_factory=list)


class EvalResults(BaseModel):
    schema_version: Literal[1] = 1
    generated_at: datetime
    videos: VideoSection
    images: ImageSection
    verdicts: VerdictSection
    latency: list[LatencyEntry] = Field(default_factory=list)
    cost: CostSection
    not_measured: list[str] = Field(default_factory=list)


# ------------------------------------------------------------------- inputs
class ManifestLine(BaseModel):
    """Ground truth for one video line, from samples/scenarios/manifest.json only."""

    scenario: str
    category: str
    true_count: int
    true_damaged: int


class ObservedLine(BaseModel):
    """What the pipeline measured for one video line (DB row or eval_counts.json row)."""

    scenario: str
    category: str
    noun_phrase: str | None = None
    observed_count: int | None = None
    flagged_damaged: int | None = None
    source: Literal["db", "eval_counts"]


class ExpectedVerdict(BaseModel):
    """Answer-key verdict for one case, from data/ground_truth.json."""

    po_number: str
    scenario_id: str | None = None
    verdict: Verdict
