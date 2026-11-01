#!/usr/bin/env python3
"""Eval: run the perception pipeline on every scenario in manifest.json.

Ground truth (true_count / true_damaged) is read ONLY from
samples/scenarios/manifest.json. Reuses the seeded deliveries 1-4 (a new
job per run, never a new delivery, so the Cases page is not polluted).
Prints cache hit/miss per stage. Writes data/eval_counts.json.

Usage: backend/.venv/bin/python scripts/eval_counts.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.infra.db.models import Delivery, PurchaseOrder  # noqa: E402
from app.infra.db.session import make_engine, make_session_factory  # noqa: E402
from app.infra.storage import LocalFileStore  # noqa: E402
from app.services.deliveries import DeliveryService  # noqa: E402
from app.services.perception import PerceptionPipeline  # noqa: E402


async def main() -> int:
    manifest = json.loads((ROOT / "samples" / "scenarios" / "manifest.json").read_text())
    settings = get_settings()
    factory = make_session_factory(make_engine())
    service = DeliveryService(factory, LocalFileStore(settings.storage_root))
    pipeline = PerceptionPipeline(settings, factory, run_decision=False)

    rows: list[dict] = []
    print(f"{'scenario':<14} {'line':<16} {'true':>4} {'obs':>4} {'phrase':>6} {'generic':>7} "
          f"{'maxv':>4} {'quality':<13} {'true_dmg':>8} {'flag_dmg':>8}  result  cache(B/SAM/D)")
    for scenario in manifest["scenarios"]:
        session = factory()
        try:
            po = session.query(PurchaseOrder).filter(
                PurchaseOrder.scenario_id == scenario["id"]).one()
            delivery = session.query(Delivery).filter(
                Delivery.scenario_id == scenario["id"]).one()
            po_id, delivery_id = po.id, delivery.id
        finally:
            session.close()

        created = service.create_job_for_delivery(delivery_id=delivery_id)
        try:
            summary = await pipeline.run(created.job_id, delivery_id)
        except Exception as exc:  # noqa: BLE001 - eval must report, not crash
            print(f"{scenario['id']:<14} PIPELINE FAILED: {type(exc).__name__}: {exc}")
            for line in scenario["lines"]:
                rows.append({"scenario": scenario["id"], "category": line["category"],
                             "true_count": line["true_count"], "observed_count": None,
                             "max_visible": None, "evidence_quality": None,
                             "true_damaged": line["true_damaged"], "flagged_damaged": None,
                             "result": "FAIL", "error": str(exc), "cache": {}})
            continue

        results_by_category = {r["category"]: r for r in summary["results"]}
        cache = summary.get("cache", {})
        cache_str = (f"B={cache.get('understanding', '?')} "
                     f"SAM={cache.get('sam', {})} D={cache.get('damage', {})}")
        for line in scenario["lines"]:
            result = results_by_category.get(line["category"])
            if result is None:  # manifest category names use spaces, DB uses underscores
                result = results_by_category.get(line["category"].replace(" ", "_"))
            if result is None:
                print(f"{scenario['id']:<14} {line['category']:<16} NO RESULT")
                rows.append({"scenario": scenario["id"], "category": line["category"],
                             "true_count": line["true_count"], "observed_count": None,
                             "max_visible": None, "evidence_quality": None,
                             "true_damaged": line["true_damaged"], "flagged_damaged": None,
                             "result": "FAIL", "error": "no perception result", "cache": cache})
                continue
            observed = result["observed_count"]
            flagged = len(result["damaged_track_ids"])
            passed = observed == line["true_count"] and flagged == line["true_damaged"]
            verdict = "PASS" if passed else "FAIL"
            phrase_obs = result.get("phrase_observed_count")
            generic_obs = result.get("generic_observed_count")
            print(f"{scenario['id']:<14} {line['category']:<16} {line['true_count']:>4} "
                  f"{observed:>4} {phrase_obs if phrase_obs is not None else '-':>6} "
                  f"{generic_obs if generic_obs is not None else '-':>7} "
                  f"{result['max_visible']:>4} {result['evidence_quality']:<13} "
                  f"{line['true_damaged']:>8} {flagged:>8}  {verdict:<6}  {cache_str}")
            rows.append({
                "scenario": scenario["id"], "category": line["category"],
                "po_line_id": result["po_line_id"], "noun_phrase": result["noun_phrase"],
                "generic_noun": result.get("generic_noun"),
                "phrase_observed_count": phrase_obs, "generic_observed_count": generic_obs,
                "true_count": line["true_count"], "observed_count": observed,
                "max_visible": result["max_visible"],
                "evidence_quality": result["evidence_quality"], "reasons": result["reasons"],
                "true_damaged": line["true_damaged"], "flagged_damaged": flagged,
                "damaged_track_ids": result["damaged_track_ids"],
                "footage_needed": result["footage_needed"],
                "result": verdict, "cache": cache,
            })
        _ = po_id

    out = ROOT / "data" / "eval_counts.json"
    out.write_text(json.dumps(rows, indent=2))
    passed = sum(1 for r in rows if r["result"] == "PASS")
    print(f"\n{passed}/{len(rows)} lines PASS -> {out.relative_to(ROOT)}")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
