#!/usr/bin/env python3
"""Run the payment-decision agent for the 4 scenario deliveries.

Needs MODEL_API_KEY (and the model IDs) in .env; perception results should
already exist (scripts/eval_counts.py) or lines fall back to GRN evidence.
Ground truth is read ONLY from data/ground_truth.json.

Usage: backend/.venv/bin/python scripts/run_decisions.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.domain.money import format_inr  # noqa: E402
from app.infra.cache import Sha256Cache  # noqa: E402
from app.infra.db.models import Delivery, PurchaseOrder  # noqa: E402
from app.infra.db.session import make_engine, make_session_factory  # noqa: E402
from app.infra.meta.client import MetaModelClient  # noqa: E402
from app.services.decision_agent import DecisionAgent  # noqa: E402


async def main() -> int:
    settings = get_settings()
    if not settings.model_api_key:
        print("MODEL_API_KEY is not set (put it in .env). Cannot run the decision agent.", file=sys.stderr)
        return 2
    try:
        config = settings.model_config_model()
    except ValueError as exc:
        print(f"Model configuration incomplete: {exc}", file=sys.stderr)
        return 2

    truth = {
        s["scenario_id"]: s
        for s in json.loads((ROOT / "data" / "ground_truth.json").read_text())["scenarios_and_discrepancies"]
        if s.get("scenario_id")
    }
    factory = make_session_factory(make_engine())
    agent = DecisionAgent(
        factory, MetaModelClient(config, cache=Sha256Cache(settings.cache_root)),
        config.decision_model, max_turns=settings.max_agent_turns,
    )
    session = factory()
    try:
        rows = (
            session.query(Delivery.id, PurchaseOrder.scenario_id)
            .join(PurchaseOrder, PurchaseOrder.id == Delivery.po_id)
            .filter(PurchaseOrder.scenario_id.isnot(None))
            .order_by(Delivery.id).all()
        )
    finally:
        session.close()

    print(f"{'scenario':<14} | {'verdict':<12} | {'amount held':>12} | {'clause':<8} | {'source':<8} | correct")
    all_ok = True
    for delivery_id, scenario_id in rows:
        expected = truth.get(scenario_id)
        read = await agent.run_standalone(delivery_id)
        clauses = sorted({ln.clause for ln in read.lines if ln.clause})
        ok = False
        if expected is not None:
            ok = read.verdict.value == expected["correct_verdict"]
            if ok and read.verdict.value == "partial_pay":
                ok = read.amount_held_paise == expected["amount_at_risk_paise"]
        all_ok = all_ok and ok
        print(f"{scenario_id:<14} | {read.verdict.value:<12} | {format_inr(read.amount_held_paise):>12} | "
              f"{','.join(clauses) or '-':<8} | {read.source:<8} | {'yes' if ok else 'no'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
