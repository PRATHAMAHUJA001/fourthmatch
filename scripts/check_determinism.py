#!/usr/bin/env python3
"""Seed twice and assert idempotency: identical files and DB content."""
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.infra.db.models import Delivery, Grn, Invoice, PoLine, PurchaseOrder, Vendor  # noqa: E402
from app.infra.db.session import make_engine, make_session_factory  # noqa: E402
from app.seed.generate import seed  # noqa: E402

KW = dict(db_path=ROOT / "data" / "fourthmatch.db",
          manifest_path=ROOT / "samples" / "scenarios" / "manifest.json",
          policy_path=ROOT / "data" / "policy" / "receiving_policy.md",
          truth_path=ROOT / "data" / "ground_truth.json")


def snapshot() -> str:
    h = hashlib.sha256()
    for f in (KW["truth_path"], KW["policy_path"]):
        h.update(f.read_bytes())
    s = make_session_factory(make_engine())()
    rows = []
    for model, fields in [(Vendor, ("code", "gstin")), (PurchaseOrder, ("po_number", "total_paise", "scenario_id")),
                          (PoLine, ("po_id", "line_no", "qty_ordered", "unit_price_paise")),
                          (Grn, ("grn_number",)), (Invoice, ("po_id", "invoice_number", "total_paise")),
                          (Delivery, ("scenario_id", "video_path"))]:
        rows += [tuple(getattr(r, f) for f in fields) for r in s.query(model).order_by(model.id).all()]
    s.close()
    h.update(repr(rows).encode())
    return h.hexdigest()


seed(**KW)
first = snapshot()
result = seed(**KW)
second = snapshot()
assert first == second, "second seed run changed state"
assert result.policy_verified and not result.truth_changed, result
print(f"PASS idempotency: two seed runs -> identical DB content and files (sha256={first[:16]}…)")
