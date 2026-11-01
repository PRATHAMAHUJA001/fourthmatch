"""Seed FourthMatch synthetic procurement data. Idempotent upsert.

    PYTHONPATH=backend backend/.venv/bin/python -m app.seed [--reset]

Sources of truth, in order:
  * samples/scenarios/manifest.json  — the 4 video scenario POs (counts only there)
  * backend/app/seed/policy_template.py — every policy clause and number
  * backend/app/seed/cases.py        — vendors, catalog, 8 document-only cases
  * data/policy/receiving_policy.md  — committed generated policy; this loader
    only verifies it against the template and refuses on mismatch. It never
    regenerates prose (that is scripts/generate_policy.py, BULK_MODEL).

Idempotent: upsert by natural keys — vendors by GSTIN, purchase orders by
po_number, invoices by (invoice_number, po_id) (invoice_number alone is not
unique: a seeded duplicate shares it), GRNs by grn_number, deliveries by
scenario_id. Seeded rows no longer in the generated set are deleted, except
rows linked to runtime data. Runtime tables (jobs, decisions, tracks,
evidence_packs, sam_runs, perception_results) are never written or deleted,
except by --reset, which drops and recreates the whole DB (dev only).
Ground-truth verdicts come from seed/expected.py (standalone, Python-only).
All arithmetic is done here in Python; counts in tracks come only from SAM.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from random import Random
from typing import Any

from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # backend/ on path

from app.domain.money import format_inr  # noqa: E402
from app.domain.schemas.seed import (  # noqa: E402
    EvalLine,
    GroundTruthCase,
    GroundTruthDocuments,
    GroundTruthGrnLine,
    GroundTruthInvoice,
    GroundTruthInvoiceLine,
    GroundTruthPoLine,
    GroundTruthTruthLine,
    GroundTruthVariance,
    ManifestScenario,
    PoLineSpec,
    PoSpec,
    SeedResult,
    SeedTotals,
)
from app.infra.db.models import (  # noqa: E402
    Decision,
    Delivery,
    EvidencePack,
    Grn,
    GrnLine,
    Invoice,
    InvoiceLine,
    PoLine,
    PurchaseOrder,
    Rule,
    SamRun,
    Track,
    Vendor,
)
from app.infra.db.session import Base, create_all, make_engine, make_session_factory  # noqa: E402
from app.seed.cases import (  # noqa: E402
    CATALOG,
    CATEGORY_DEFAULT_ITEM,
    CATEGORY_DEFAULT_PRICE_PAISE,
    CATEGORY_VENDOR_CODE,
    DOCUMENT_CASES,
    DRIVERS,
    STOREKEEPERS,
    VENDOR_CATEGORY,
    VENDORS,
    catalog_line,
)
from app.seed.expected import expected_verdict  # noqa: E402
from app.seed.manifest import load_manifest  # noqa: E402
from app.seed.policy_template import POLICY, RULE_SPECS, check_policy  # noqa: E402

SEED = 42
TOTAL_POS = 30
REPO_ROOT = Path(__file__).resolve().parents[3]
GST_PCT = 18  # computed in Python; PO totals ex-GST, invoice totals include it


def _spec_line(category: str, item: int, qty: int, price_paise: int) -> PoLineSpec:
    return catalog_line(category, item, qty, price_paise, POLICY["quantity_tolerance_pct"][category])


def build_po_data(manifest: list[ManifestScenario], rng: Random) -> list[PoSpec]:
    """Pure-Python build of all 30 POs (no DB). Deterministic for Random(42)."""
    pos: list[PoSpec] = []

    # 1) The 4 scenario POs, from the manifest and nothing else.
    for scn in manifest:
        lines = [
            _spec_line(ml.category, CATEGORY_DEFAULT_ITEM[ml.category], ml.po_qty,
                       CATEGORY_DEFAULT_PRICE_PAISE[ml.category])
            for ml in scn.lines
        ]
        highest = max(lines, key=lambda line: line.qty * line.price_paise)
        pos.append(PoSpec(vendor_code=CATEGORY_VENDOR_CODE[highest.category],
                          scenario_id=scn.scenario_id, video=scn.video_path, lines=lines))

    # 2) The 8 document-only cases (PO-005..PO-012).
    for case in DOCUMENT_CASES:
        lines = [_spec_line(cat, item, qty, price) for cat, item, qty, price in case.lines]
        pos.append(PoSpec(vendor_code=case.vendor_code, lines=lines, doc_case=case))

    # 3) Remaining clean POs, deterministic under the caller's rng.
    qty_range = {"cartons": (10, 200), "bagged_material": (20, 500), "steel_coils": (2, 24)}
    vendor_codes = [v.code for v in VENDORS]
    while len(pos) < TOTAL_POS:
        vendor_code = vendor_codes[rng.randrange(len(vendor_codes))]
        category = VENDOR_CATEGORY[vendor_code] if rng.random() < 0.8 else rng.choice(list(CATALOG))
        lines = []
        for _ in range(rng.choice([1, 1, 1, 2])):
            items = CATALOG[category]
            item_index = rng.randrange(len(items))
            item = items[item_index]
            lo, hi = qty_range[category]
            lines.append(_spec_line(category, item_index, rng.randint(lo, hi),
                                    rng.randrange(item.price[0], item.price[1] + 1, 100)))
            if rng.random() < 0.25:
                category = rng.choice([c for c in CATALOG if c != category])
        pos.append(PoSpec(vendor_code=vendor_code, lines=lines))

    # Dates, invoice numbers, per-line doc quantities — all precomputed.
    base_date = date(2026, 4, 6)
    inv_counter: dict[str, int] = {}
    invoice_numbers: dict[int, str] = {}
    manifest_by_id = {scn.scenario_id: scn for scn in manifest}
    for idx, po in enumerate(pos):
        if po.scenario_id:
            po.order_date = date(2026, 10, 5) + timedelta(days=idx)
        else:
            po.order_date = base_date + timedelta(days=rng.randrange(0, 190))
        po.expected_days = rng.choice([7, 10, 14])
        po.received_date = po.order_date + timedelta(days=rng.choice([5, 7, 9]))
        po.vehicle_no = f"MH-12-{rng.choice(['AB', 'CD', 'EF'])}-{rng.randrange(1000, 9999)}"
        inv_counter[po.vendor_code] = inv_counter.get(po.vendor_code, 0) + 1
        number = f"{po.vendor_code}/26-27/{inv_counter[po.vendor_code]:03d}"
        doc_case_ctx = po.doc_case
        if doc_case_ctx and doc_case_ctx.type == "duplicate_invoice_number" and doc_case_ctx.duplicates_po_index is not None:
            number = invoice_numbers[doc_case_ctx.duplicates_po_index]
        invoice_numbers[idx] = number
        po.invoice_number = number

        scenario_ctx = manifest_by_id.get(po.scenario_id) if po.scenario_id else None
        eval_lines: list[EvalLine] = []
        for j, ln in enumerate(po.lines):
            if scenario_ctx is not None:
                ml = scenario_ctx.lines[j]
                eval_lines.append(EvalLine(
                    category=ln.category, po_qty=ml.po_qty, grn_qty=ml.grn_qty, grn_damaged=0,
                    inv_qty=ml.invoice_qty, po_price_paise=ln.price_paise,
                    inv_price_paise=ln.price_paise, truth_qty=ml.truth_qty,
                    truth_damaged=ml.truth_damaged))
                continue
            grn_qty, grn_dmg = ln.qty, 0
            inv_qty, inv_price = ln.qty, ln.price_paise
            if doc_case_ctx:
                if doc_case_ctx.grn_pct is not None:  # integer-percent floor/ceil, no floats
                    pct = doc_case_ctx.grn_pct
                    grn_qty = (ln.qty * pct) // 100 if pct < 100 else -(-ln.qty * pct // 100)
                if doc_case_ctx.type == "damaged_invoiced_in_full":
                    grn_dmg = doc_case_ctx.damaged
                if doc_case_ctx.price_multiplier is not None:
                    inv_price = round(ln.price_paise * doc_case_ctx.price_multiplier / 100) * 100
                if doc_case_ctx.qty_pct is not None:
                    inv_qty = -(-ln.qty * doc_case_ctx.qty_pct // 100)
                if doc_case_ctx.invoice_follows_grn:
                    inv_qty = grn_qty
            eval_lines.append(EvalLine(
                category=ln.category, po_qty=ln.qty, grn_qty=grn_qty, grn_damaged=grn_dmg,
                inv_qty=inv_qty, po_price_paise=ln.price_paise, inv_price_paise=inv_price))
        po.eval_lines = eval_lines
        po.verdict = expected_verdict(
            eval_lines, duplicate=bool(doc_case_ctx and doc_case_ctx.type == "duplicate_invoice_number"))
    return pos


def _upsert(session: Session, model: Any, key: dict[str, Any], values: dict[str, Any]) -> Any:
    row = session.query(model).filter_by(**key).first()
    if row is None:
        row = model(**key, **values)
        session.add(row)
    else:
        for attr, attr_value in values.items():
            setattr(row, attr, attr_value)
    session.flush()
    return row


def _delivery_has_runtime(session: Session, delivery_id: int) -> bool:
    return bool(
        session.query(Track).filter_by(delivery_id=delivery_id).first()
        or session.query(SamRun).filter_by(delivery_id=delivery_id).first()
    )


def _po_has_runtime(session: Session, po: PurchaseOrder) -> bool:
    if session.query(Decision).filter_by(po_id=po.id).first():
        return True
    if session.query(EvidencePack).filter_by(po_id=po.id).first():
        return True
    return any(_delivery_has_runtime(session, d.id) for d in po.deliveries)


def _prune_stale(session: Session, pos: list[PoSpec], po_rows: list[PurchaseOrder]) -> None:
    """Delete seeded rows no longer generated. Runtime-linked rows are kept."""
    desired_po_numbers = {f"FM/PO/26-27/{i + 1:03d}" for i in range(len(pos))}
    desired_po_ids = {po.id for po in po_rows}
    desired_grn_numbers = {f"GRN-2026-{i + 1:04d}" for i in range(len(pos))}
    desired_invoice_keys = {(spec.invoice_number, po.id) for spec, po in zip(pos, po_rows, strict=True)}
    desired_scenarios = {p.scenario_id for p in pos if p.scenario_id}
    desired_gstins = {v.gstin for v in VENDORS}

    for grn in session.query(Grn).filter(Grn.po_id.in_(desired_po_ids)).all():
        if grn.grn_number not in desired_grn_numbers:
            linked = session.query(Delivery).filter_by(grn_id=grn.id).first()
            if linked and _delivery_has_runtime(session, linked.id):
                continue
            session.delete(grn)
    for inv in session.query(Invoice).filter(Invoice.po_id.in_(desired_po_ids)).all():
        if (inv.invoice_number, inv.po_id) not in desired_invoice_keys:
            session.delete(inv)
    for delivery in session.query(Delivery).filter(Delivery.scenario_id.isnot(None)).all():
        if delivery.scenario_id not in desired_scenarios and not _delivery_has_runtime(session, delivery.id):
            session.delete(delivery)
    session.flush()

    for po in session.query(PurchaseOrder).filter_by(synthetic=True).all():
        if po.po_number not in desired_po_numbers and not _po_has_runtime(session, po):
            session.delete(po)
    session.flush()
    for vendor in session.query(Vendor).filter_by(synthetic=True).all():
        if vendor.gstin not in desired_gstins:
            if not session.query(PurchaseOrder).filter_by(vendor_id=vendor.id).first():
                session.delete(vendor)
    session.flush()


def seed(db_path: Path, manifest_path: Path, policy_path: Path, truth_path: Path,
         *, reset: bool = False) -> SeedResult:
    # Policy first: verify the committed file, refuse on mismatch. Never write it.
    if not policy_path.exists():
        raise FileNotFoundError(
            f"policy file missing: {policy_path} — run scripts/generate_policy.py first")
    check = check_policy(policy_path.read_text())
    if not check.ok:
        raise RuntimeError(
            f"policy {policy_path} does not match policy_template "
            f"(mismatched={check.mismatched}, missing={check.missing}, header_ok={check.header_ok}) "
            "— regenerate with scripts/generate_policy.py; the seed never rewrites policy")

    rng = Random(SEED)
    manifest = load_manifest(manifest_path, repo_root=REPO_ROOT)
    pos = build_po_data(manifest, rng)

    engine = make_engine(db_path)
    if reset:  # dev only: wipe the whole DB, runtime tables included
        Base.metadata.drop_all(engine)
    create_all(engine)
    session = make_session_factory(engine)()
    try:
        vendors = {}
        for v in VENDORS:  # natural key: GSTIN
            vendors[v.code] = _upsert(session, Vendor, {"gstin": v.gstin},
                                      {"code": v.code, "name": v.name, "city": v.city,
                                       "state": v.state, "primary_category": v.primary_category,
                                       "contact_name": v.contact_name, "contact_email": v.contact_email,
                                       "payment_terms_days": POLICY["payment_terms_days"],
                                       "synthetic": True})
        desired_rules = {(r["clause"], r["category"], r["rule_type"]) for r in RULE_SPECS}
        for rule in session.query(Rule).filter_by(policy_version=POLICY["policy_version"]).all():
            if (rule.clause, rule.category, rule.rule_type) not in desired_rules:
                session.delete(rule)
        for r in RULE_SPECS:
            _upsert(session, Rule,
                    {"clause": r["clause"], "category": r["category"], "rule_type": r["rule_type"]},
                    {"policy_version": POLICY["policy_version"], "threshold_pct": r["threshold_pct"],
                     "action": r["action"], "description": r["description"]})

        ground_truth: list[GroundTruthCase] = []
        totals = SeedTotals()
        po_rows: list[PurchaseOrder] = []
        for idx, data in enumerate(pos):
            assert data.verdict is not None and data.order_date and data.received_date
            po_number = f"FM/PO/26-27/{idx + 1:03d}"
            case, result = data.doc_case, data.verdict
            # natural key: po_number
            po = _upsert(session, PurchaseOrder, {"po_number": po_number},
                         {"vendor_id": vendors[data.vendor_code].id,
                          "order_date": data.order_date,
                          "expected_date": data.order_date + timedelta(days=data.expected_days),
                          "scenario_id": data.scenario_id, "status": "received", "synthetic": True})
            po_rows.append(po)
            po_total = 0
            po_lines = []
            existing_lines = {line.line_no: line for line in po.lines}
            for line_no, ln in enumerate(data.lines, start=1):
                total = ln.qty * ln.price_paise
                po_total += total
                values = {"category": ln.category, "sku": ln.sku, "description": ln.description,
                          "unit": ln.unit, "qty_ordered": ln.qty,
                          "unit_price_paise": ln.price_paise, "tolerance_pct": ln.tolerance_pct,
                          "line_total_paise": total}
                if line_no in existing_lines:
                    row = existing_lines[line_no]
                    for attr, attr_value in values.items():
                        setattr(row, attr, attr_value)
                else:
                    row = PoLine(po_id=po.id, line_no=line_no, **values)
                    session.add(row)
                po_lines.append(row)
            for line_no, row in existing_lines.items():
                if line_no > len(data.lines):
                    session.delete(row)
            session.flush()
            po.total_paise = po_total
            totals.po_value_paise += po_total

            grn = _upsert(session, Grn, {"grn_number": f"GRN-2026-{idx + 1:04d}"},
                          {"po_id": po.id, "received_date": data.received_date,
                           "storekeeper_name": STOREKEEPERS[idx % len(STOREKEEPERS)], "signed": True,
                           "notes": "Damaged units noted at dock; billed in full by vendor."
                                    if case and case.type == "damaged_invoiced_in_full" else None})
            # natural key: (invoice_number, po_id) — invoice_number alone is not
            # unique, the seeded duplicate shares it with an earlier PO's invoice.
            invoice = _upsert(session, Invoice, {"invoice_number": data.invoice_number, "po_id": po.id},
                              {"vendor_id": po.vendor_id,
                               "invoice_date": data.received_date + timedelta(days=1),
                               "due_date": data.received_date + timedelta(days=1 + POLICY["payment_terms_days"]),
                               "total_paise": 0,
                               "status": "held" if case or (data.scenario_id and result.verdict != "approve") else "pending"})
            for ev, po_line in zip(data.eval_lines, po_lines, strict=True):
                _upsert(session, GrnLine, {"grn_id": grn.id, "po_line_id": po_line.id},
                        {"qty_received": ev.grn_qty, "qty_damaged": ev.grn_damaged})
                _upsert(session, InvoiceLine, {"invoice_id": invoice.id, "po_line_id": po_line.id},
                        {"qty_invoiced": ev.inv_qty, "unit_price_paise": ev.inv_price_paise,
                         "line_total_paise": ev.inv_qty * ev.inv_price_paise})
            subtotal = sum(line.inv_qty * line.inv_price_paise for line in data.eval_lines)
            invoice.gst_paise = round(subtotal * GST_PCT / 100)
            invoice.total_paise = subtotal + invoice.gst_paise

            if data.scenario_id:  # natural key: scenario_id
                _upsert(session, Delivery, {"scenario_id": data.scenario_id},
                        {"po_id": po.id, "grn_id": grn.id, "video_path": data.video,
                         "delivered_at": datetime.combine(data.received_date, time(10, 30), tzinfo=UTC),
                         "vehicle_no": data.vehicle_no,
                         "driver_name": DRIVERS[idx % len(DRIVERS)], "status": "recorded"})

            if data.scenario_id or case:
                totals.at_risk_paise += result.amount_at_risk_paise
                ground_truth.append(GroundTruthCase(
                    po_number=po_number, scenario_id=data.scenario_id,
                    source="video" if data.scenario_id else "documents_only",
                    video_path=data.video, vendor=vendors[data.vendor_code].name,
                    documents=GroundTruthDocuments(
                        po=[GroundTruthPoLine(qty=line.po_qty, unit=spec.unit, category=line.category)
                            for line, spec in zip(data.eval_lines, data.lines, strict=True)],
                        grn=[GroundTruthGrnLine(qty=line.grn_qty, damaged=line.grn_damaged)
                             for line in data.eval_lines],
                        invoice=GroundTruthInvoice(
                            number=data.invoice_number,
                            lines=[GroundTruthInvoiceLine(qty=line.inv_qty,
                                                          unit_price_inr=line.inv_price_paise / 100)
                                   for line in data.eval_lines],
                            total_paise=invoice.total_paise)),
                    truth=([GroundTruthTruthLine(qty=line.truth_qty or 0, damaged=line.truth_damaged,
                                                 unit=spec.unit)
                            for line, spec in zip(data.eval_lines, data.lines, strict=True)]
                           if data.scenario_id else None),
                    discrepancy_types=result.discrepancy_types,
                    seeded_type=(case.type if case else None),
                    is_discrepancy=bool(result.discrepancy_types),
                    correct_verdict=result.verdict,
                    policy_clauses=result.policy_clauses,
                    variance=[GroundTruthVariance(qty=line.variance_qty, pct=line.variance_pct)
                              for line in result.per_line],
                    amount_at_risk_paise=result.amount_at_risk_paise,
                    amount_at_risk_inr=format_inr(result.amount_at_risk_paise),
                    requires_debit_note=result.requires_debit_note,
                    debit_qty=result.debit_qty))
            else:
                assert result.verdict == "approve", f"clean PO {po_number} not approve: {result}"

        _prune_stale(session, pos, po_rows)

        clean_pos = [f"FM/PO/26-27/{i + 1:03d}" for i, d in enumerate(pos)
                     if not d.scenario_id and not d.doc_case]
        truth_doc = {
            "seed": SEED, "policy_version": POLICY["policy_version"],
            "policy_numbers": POLICY, "gst_pct_on_invoices": GST_PCT,
            "manifest": str(manifest_path.relative_to(REPO_ROOT)) if manifest_path.is_relative_to(REPO_ROOT) else str(manifest_path),
            "amount_basis": "amount_at_risk is ex-GST, computed in Python (backend/app/seed/expected.py)",
            "verdict_vocabulary": ["approve", "partial_pay", "hold"],
            "scenarios_and_discrepancies": [c.model_dump() for c in ground_truth],
            "clean_po_numbers": clean_pos,
            "notes": [
                "Scenario counts come only from samples/scenarios/manifest.json; live counts must come only from SAM tracks.",
                "Verdicts are computed standalone in backend/app/seed/expected.py from policy_template tolerances (no runtime decision-path code).",
                "Decisions, tracks and evidence packs are intentionally unseeded — the agent creates them.",
            ],
        }
        truth_text = json.dumps(truth_doc, indent=2) + "\n"
        truth_changed = not truth_path.exists() or truth_path.read_text() != truth_text
        if truth_changed:
            truth_path.parent.mkdir(parents=True, exist_ok=True)
            truth_path.write_text(truth_text)
        session.commit()
        counts = {t: session.query(m).count() for t, m in
                  [("vendors", Vendor), ("purchase_orders", PurchaseOrder), ("po_lines", PoLine),
                   ("grns", Grn), ("invoices", Invoice), ("deliveries", Delivery), ("rules", Rule)]}
        return SeedResult(counts=counts, ground_truth=ground_truth, totals=totals,
                          clean_count=len(clean_pos), policy_verified=True,
                          truth_changed=truth_changed)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Seed FourthMatch synthetic data (idempotent upsert).")
    ap.add_argument("--db", type=Path, default=REPO_ROOT / "data" / "fourthmatch.db")
    ap.add_argument("--manifest", type=Path, default=REPO_ROOT / "samples" / "scenarios" / "manifest.json")
    ap.add_argument("--policy", type=Path, default=REPO_ROOT / "data" / "policy" / "receiving_policy.md")
    ap.add_argument("--ground-truth", type=Path, default=REPO_ROOT / "data" / "ground_truth.json")
    ap.add_argument("--reset", action="store_true",
                    help="DEV ONLY: drop and recreate the whole DB (wipes runtime tables too)")
    args = ap.parse_args(argv)
    args.db.parent.mkdir(parents=True, exist_ok=True)

    result = seed(args.db, args.manifest, args.policy, args.ground_truth, reset=args.reset)
    c, t = result.counts, result.totals
    print(f"Seeded {args.db} (seed={SEED}, idempotent upsert{', RESET' if args.reset else ''}; manifest={args.manifest.name})")
    print(f"  vendors={c['vendors']}  purchase_orders={c['purchase_orders']}  po_lines={c['po_lines']}  "
          f"grns={c['grns']}  invoices={c['invoices']}  deliveries(video)={c['deliveries']}  rules={c['rules']}")
    print(f"  policy: {args.policy}  [verified against policy_template; loader never regenerates]")
    print(f"  ground truth: {args.ground_truth}  ({len(result.ground_truth)} cases, {result.clean_count} clean POs)"
          f"{' (file updated)' if result.truth_changed else ' (unchanged)'}")
    print(f"  total PO value (ex-GST): {format_inr(t.po_value_paise)}   "
          f"seeded amount at risk (ex-GST): {format_inr(t.at_risk_paise)}")
    print()
    print(f"  {'PO':<16} {'Scenario / type':<38} {'Verdict':<13} {'Clauses':<12} At risk")
    print(f"  {'-' * 16} {'-' * 38} {'-' * 13} {'-' * 12} {'-' * 12}")
    for e in result.ground_truth:
        label = e.scenario_id or ", ".join(e.discrepancy_types)
        print(f"  {e.po_number:<16} {label:<38} {e.correct_verdict:<13} "
              f"{','.join(e.policy_clauses):<12} {e.amount_at_risk_inr}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
