#!/usr/bin/env python3
"""Export approved rules + SAM tracks from the local DB to data/demo/snapshot.json.

Run on the machine that did the real run (Pratham's Mac), then commit the file.
`python -m app.seed --demo` on the server reads it, so the public demo shows the
real compiled rules and track ids with no model call and no storage/ cache.

Usage: PYTHONPATH=backend backend/.venv/bin/python scripts/export_demo_snapshot.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.infra.db.models import Delivery, PerceptionResult, Track  # noqa: E402
from app.infra.db.repositories.cases import SqlCaseRepository  # noqa: E402
from app.infra.db.session import make_engine, make_session_factory  # noqa: E402
from app.seed.demo import SNAPSHOT_PATH  # noqa: E402
from app.services.case_facts import approved_rules  # noqa: E402


def main() -> int:
    session = make_session_factory(make_engine())()
    try:
        rules, version = approved_rules(SqlCaseRepository(session))
        if not rules:
            print("No approved rules in the DB: compile + approve the policy first.", file=sys.stderr)
            return 1
        tracks = []
        results = session.query(PerceptionResult).order_by(PerceptionResult.id).all()
        for result in results:
            delivery = session.get(Delivery, result.delivery_id)
            if delivery is None or not delivery.scenario_id:
                continue
            for t in session.query(Track).filter_by(sam_run_id=result.sam_run_id).order_by(Track.id):
                tracks.append({
                    "scenario": delivery.scenario_id, "category": result.category,
                    "object_id": t.object_id, "first_frame": t.first_frame,
                    "last_frame": t.last_frame, "frame_count": t.frame_count,
                    "confidence": t.confidence,
                })
        SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT_PATH.write_text(json.dumps(
            {"policy_version": version, "rules": [r.model_dump(mode="json") for r in rules],
             "tracks": tracks}, indent=2) + "\n")
        print(f"wrote {SNAPSHOT_PATH.relative_to(ROOT)}: {len(rules)} rules, {len(tracks)} tracks")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
