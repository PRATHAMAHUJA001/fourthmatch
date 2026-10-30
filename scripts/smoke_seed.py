#!/usr/bin/env python3
"""Smoke test for the seed. Derives every expectation from the manifest —
no scenario count is hardcoded here either.

Usage: PYTHONPATH=backend backend/.venv/bin/python scripts/smoke_seed.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.infra.db.models import Delivery, Grn, Invoice, PurchaseOrder, Vendor  # noqa: E402
from app.infra.db.session import make_engine, make_session_factory  # noqa: E402
from app.seed.manifest import load_manifest  # noqa: E402

manifest = load_manifest(ROOT / "samples" / "scenarios" / "manifest.json", repo_root=ROOT)
truth = json.loads((ROOT / "data" / "ground_truth.json").read_text())
entries = truth["scenarios_and_discrepancies"]
scn_entries = {e["scenario_id"]: e for e in entries if e["scenario_id"]}
doc_entries = [e for e in entries if not e["scenario_id"]]

assert len(entries) == len(manifest) + 8, "ground truth must hold manifest scenarios + 8 document cases"
assert len(doc_entries) == 8 and len(truth["clean_po_numbers"]) == 30 - len(entries)
assert all(e["correct_verdict"] in {"hold_payment", "partial_pay"} for e in doc_entries)

s = make_session_factory(make_engine())()
assert s.query(Vendor).count() == 4
assert s.query(PurchaseOrder).count() == 30
assert s.query(Grn).count() == 30 and s.query(Invoice).count() == 30
assert s.query(Delivery).count() == len(manifest)
for v in s.query(Vendor).all():
    assert len(v.gstin) == 15 and "FAKE" in v.gstin, v.gstin
for scn in manifest:
    po = s.query(PurchaseOrder).filter_by(scenario_id=scn.scenario_id).one()
    assert [line.qty_ordered for line in po.lines] == [line.po_qty for line in scn.lines], scn.scenario_id
    e = scn_entries[scn.scenario_id]
    assert [t["qty"] for t in e["truth"]] == [line.truth_qty for line in scn.lines]
    assert [g["qty"] for g in e["documents"]["grn"]] == [line.grn_qty for line in scn.lines]
    delivery = s.query(Delivery).filter_by(scenario_id=scn.scenario_id).one()
    assert delivery.video_path == scn.video_path and (ROOT / delivery.video_path).exists()
s.close()
print(f"PASS smoke_seed: manifest scenarios={len(manifest)} match DB POs, "
      f"ground truth cases={len(entries)} (8 document-only), vendors=4, POs/GRNs/invoices=30")
