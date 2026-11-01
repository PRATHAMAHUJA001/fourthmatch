"""Typed readers/writers for the eval data files. No models, no DB."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import TypeAdapter

from app.domain.enums import Verdict
from app.domain.schemas.eval import EvalImageLabel, EvalResults, ExpectedVerdict, ManifestLine, ObservedLine

_LABELS: TypeAdapter[list[EvalImageLabel]] = TypeAdapter(list[EvalImageLabel])


def load_labels(path: Path) -> list[EvalImageLabel]:
    if not path.exists():
        return []
    return _LABELS.validate_json(path.read_bytes())


def save_labels(path: Path, labels: list[EvalImageLabel]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_LABELS.dump_json(labels, indent=2) + b"\n")


def load_manifest(path: Path) -> list[ManifestLine]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [
        ManifestLine(scenario=s["id"], category=ln["category"], true_count=ln["true_count"],
                     true_damaged=ln["true_damaged"])
        for s in raw["scenarios"]
        for ln in s["lines"]
    ]


def load_expected_verdicts(path: Path) -> list[ExpectedVerdict]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [
        ExpectedVerdict(po_number=c["po_number"], scenario_id=c.get("scenario_id"),
                        verdict=Verdict(c["correct_verdict"]))
        for c in raw["scenarios_and_discrepancies"]
    ]


def load_eval_counts(path: Path) -> list[ObservedLine]:
    """Observed side of data/eval_counts.json (its own true_count fields are ignored)."""
    if not path.exists():
        return []
    return [
        ObservedLine(scenario=r["scenario"], category=r["category"], noun_phrase=r.get("noun_phrase"),
                     observed_count=r.get("observed_count"), flagged_damaged=r.get("flagged_damaged"),
                     source="eval_counts")
        for r in json.loads(path.read_text(encoding="utf-8"))
    ]


def load_results(path: Path) -> EvalResults | None:
    if not path.exists():
        return None
    return EvalResults.model_validate_json(path.read_bytes())


def save_results(path: Path, results: EvalResults) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(results.model_dump_json(indent=2).encode() + b"\n")
