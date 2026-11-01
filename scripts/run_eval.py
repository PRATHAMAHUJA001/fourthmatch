#!/usr/bin/env python3
"""Full eval from already-stored evidence. Makes NO model calls and needs no API key.

Reads: samples/scenarios/manifest.json (video ground truth), data/ground_truth.json
(verdict answer key), data/eval_counts.json and the perception_results / decisions /
model_calls tables (what was measured), data/eval_images/labels.json (synthetic
stills; only images with a human-confirmed true_count are scored).
Writes: data/eval_results.json (EvalResults schema) and prints a table.
Anything not measured is reported as "—" with the reason, never invented.

Cost: set MODEL_COST_RATES='{"<model id>": {"input_per_1m": x, "output_per_1m": y}}' and
MODEL_COST_CURRENCY=<code> (env or .env). Unset -> cost is "not measured"; no price is assumed.

Seed first on a fresh checkout:  cd backend && .venv/bin/python -m app.seed
Usage: backend/.venv/bin/python scripts/run_eval.py [--out PATH]
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from app.domain.enums import Verdict  # noqa: E402
from app.domain.metrics import parse_cost_rates  # noqa: E402
from app.domain.schemas.eval import EvalResults, VerdictScore  # noqa: E402
from app.infra.db.repositories.cases import SqlCaseRepository  # noqa: E402
from app.infra.db.repositories.evaluation import SqlEvaluationRepository  # noqa: E402
from app.infra.db.session import make_engine, make_session_factory  # noqa: E402
from app.services.cases import CaseService  # noqa: E402
from app.services.eval_files import (  # noqa: E402
    load_eval_counts,
    load_expected_verdicts,
    load_labels,
    load_manifest,
    save_results,
)
from app.services.eval_report import collect_eval_results  # noqa: E402

DASH = "—"


def _n(v: object) -> str:
    return DASH if v is None else str(v)


def _pct(v: float | None) -> str:
    return DASH if v is None else f"{v * 100:.1f}%"


def _f(v: float | None, digits: int = 2) -> str:
    return DASH if v is None else f"{v:.{digits}f}"


def _print_verdict_score(title: str, score: VerdictScore) -> None:
    print(f"\n{title}: {score.cases_correct}/{score.cases_total} correct, accuracy {_pct(score.accuracy)}")
    print(f"  {'verdict':<14} {'precision':>9} {'recall':>7} {'f1':>6} {'support':>8}")
    for m in score.per_class:
        print(f"  {m.label.value:<14} {_f(m.precision):>9} {_f(m.recall):>7} {_f(m.f1):>6} {m.support:>8}")
    print(f"  {'macro':<14} {_f(score.macro_precision):>9} {_f(score.macro_recall):>7} {_f(score.macro_f1):>6}")
    labels = [lb.value for lb in score.confusion.labels]
    print("  confusion (rows = truth, cols = predicted): " + " ".join(f"{lb[:8]:>8}" for lb in labels))
    for lb, row in zip(labels, score.confusion.matrix, strict=True):
        print(f"    {lb:<41} " + " ".join(f"{c:>8}" for c in row))


def print_report(r: EvalResults) -> None:
    v = r.videos
    print("=== Video counts (SAM tracks merged in Python vs samples/scenarios/manifest.json) ===")
    print(f"{'scenario':<14} {'category':<16} {'true':>4} {'obs':>4} {'dmg true':>8} {'dmg flag':>8}  {'ok':<4} source")
    for row in v.rows:
        ok = DASH if row.count_correct is None else ("yes" if row.count_correct and row.damage_correct else "no")
        print(f"{row.scenario:<14} {row.category:<16} {row.true_count:>4} {_n(row.observed_count):>4} "
              f"{row.true_damaged:>8} {_n(row.flagged_damaged):>8}  {ok:<4} {row.source}")
    cs, ds = v.count_summary, v.damage_summary
    print(f"count accuracy {_pct(cs.accuracy)} ({cs.correct}/{cs.measured} measured of {cs.n}), "
          f"MAE {_f(cs.mean_abs_error)}; damage accuracy {_pct(ds.accuracy)} ({ds.correct}/{ds.measured})")

    i = r.images
    print("\n=== Eval images (SYNTHETIC; scored only where a human confirmed true_count) ===")
    print(f"images {i.images_total}, confirmed {i.images_confirmed}")
    for row in i.rows:
        ok = DASH if row.correct is None else ("yes" if row.correct else "no")
        print(f"{row.id:<6} {row.phrase:<14} prompted {row.prompted_count:>2}  sam {_n(row.sam_count):>3}  true {row.true_count:>2}  {ok}")
    print(f"count accuracy {_pct(i.summary.accuracy)} ({i.summary.correct}/{i.summary.measured}), "
          f"MAE {_f(i.summary.mean_abs_error)}")

    print("\n=== Verdicts (12 cases vs data/ground_truth.json) ===")
    if r.verdicts.served:
        _print_verdict_score("Served (Python recompute)", r.verdicts.served)
    else:
        print(f"Served (Python recompute): {DASH}  not measured: {r.verdicts.served_reason}")
    if r.verdicts.agent:
        _print_verdict_score("Agent (stored decisions)", r.verdicts.agent)
    else:
        print(f"Agent (stored decisions): {DASH}  not measured: {r.verdicts.agent_reason}")

    print("\n=== Latency per model (live calls only) ===")
    if r.latency:
        print(f"{'model':<26} {'role':<26} {'calls':>5} {'live':>5} {'p50 ms':>8} {'p95 ms':>8}")
        for row in r.latency:
            print(f"{row.model:<26} {row.role:<26} {row.calls:>5} {row.live_calls:>5} "
                  f"{_f(row.p50_ms, 0):>8} {_f(row.p95_ms, 0):>8}")
    else:
        print(DASH + "  no model_calls rows")

    c = r.cost
    print("\n=== Cost ===")
    print(f"tokens in/out {c.total_input_tokens}/{c.total_output_tokens}; deliveries processed {c.deliveries_processed}; "
          f"total {_f(c.total_cost, 4)} {c.currency or ''}; per delivery {_f(c.cost_per_delivery, 4)} {c.currency or ''}".rstrip())

    print("\n=== Not measured ===")
    for line in r.not_measured or ["(everything measured)"]:
        print(f"- {line}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "eval_results.json")
    args = parser.parse_args()

    try:
        rates = parse_cost_rates(os.environ.get("MODEL_COST_RATES"))
    except ValueError as exc:
        print(f"{exc}", file=sys.stderr)
        return 1
    currency = os.environ.get("MODEL_COST_CURRENCY", "").strip() or None

    manifest = load_manifest(ROOT / "samples" / "scenarios" / "manifest.json")
    expected = load_expected_verdicts(ROOT / "data" / "ground_truth.json")
    labels = load_labels(ROOT / "data" / "eval_images" / "labels.json")

    factory = make_session_factory(make_engine())
    session = factory()
    try:
        cases = CaseService(SqlCaseRepository(session))
        served: dict[str, Verdict | None] = {c.po_number: c.verdict for c in cases.list_cases()}
        results = collect_eval_results(
            SqlEvaluationRepository(session),
            manifest=manifest,
            exported_counts=load_eval_counts(ROOT / "data" / "eval_counts.json"),
            labels=labels, expected=expected, served=served, rates=rates, currency=currency,
        )
    finally:
        session.close()

    save_results(args.out, results)
    print_report(results)
    try:
        shown = args.out.relative_to(ROOT)
    except ValueError:
        shown = args.out
    print(f"\nWrote {shown}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
