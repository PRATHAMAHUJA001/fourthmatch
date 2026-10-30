"""Declarative seed data: vendors, catalog, and the 8 document-only cases.

Scenario POs are NOT here — they come from samples/scenarios/manifest.json.
Document cases carry their own base quantities (they have no video); their
verdicts are computed from policy_template tolerances in seed/expected.py,
never asserted here. Multipliers are integer percents where noted.
"""
from __future__ import annotations

from app.domain.schemas.seed import CatalogItem, DocumentCase, PoLineSpec, VendorSpec

VENDORS: list[VendorSpec] = [
    VendorSpec(code="VND-001", name="Shree Ganesh Packaging Industries", gstin="27FAKEX4821P1Z5",
               city="Pune", state="Maharashtra", primary_category="cartons",
               contact_name="Nikhil Deshmukh", contact_email="dispatch@shreeganeshpkg.example.in"),
    VendorSpec(code="VND-002", name="Deccan Polymers & Bagging Co.", gstin="36FAKEP7392D1Z8",
               city="Hyderabad", state="Telangana", primary_category="bagged_material",
               contact_name="Farhan Sheikh", contact_email="sales@deccanpolymers.example.in"),
    VendorSpec(code="VND-003", name="Bharat Steel Rolling Mills Ltd.", gstin="27FAKES1056R1Z3",
               city="Mumbai", state="Maharashtra", primary_category="steel_coils",
               contact_name="Meera Krishnan", contact_email="orders@bharatsteel.example.in"),
    VendorSpec(code="VND-004", name="Kaveri Agro Commodities Pvt. Ltd.", gstin="29FAKEA8840K1Z6",
               city="Bengaluru", state="Karnataka", primary_category="bagged_material",
               contact_name="Divya Raman", contact_email="supply@kaveriagro.example.in"),
]
# GSTINs are format-valid (15 chars) but clearly fake: the PAN segment spells FAKE.

CATALOG: dict[str, list[CatalogItem]] = {
    "cartons": [
        CatalogItem(sku="CTN-3PLY-18", description="Corrugated carton 3-ply 18x12x12 in", unit="box", price=(18_000, 32_000)),
        CatalogItem(sku="CTN-5PLY-24", description="Corrugated carton 5-ply 24x18x18 in", unit="box", price=(42_000, 68_000)),
        CatalogItem(sku="CTN-DIE-A4", description="Die-cut carton A4 document size", unit="box", price=(25_000, 45_000)),
    ],
    "bagged_material": [
        CatalogItem(sku="BAG-PPGR-25", description="PP granules bag 25 kg", unit="bag", price=(78_000, 1_45_000)),
        CatalogItem(sku="BAG-LDPE-25", description="LDPE pellets bag 25 kg", unit="bag", price=(65_000, 1_20_000)),
        CatalogItem(sku="BAG-CEM-50", description="Cement bag 50 kg OPC", unit="bag", price=(34_000, 42_000)),
    ],
    "steel_coils": [
        CatalogItem(sku="STL-HR-1250", description="HR steel coil 1250 mm x 3 mm", unit="coil", price=(5_80_000_00, 7_40_000_00)),
        CatalogItem(sku="STL-CR-1000", description="CR steel coil 1000 mm x 1.6 mm", unit="coil", price=(6_50_000_00, 9_20_000_00)),
        CatalogItem(sku="STL-GI-1220", description="GI steel coil 1220 mm x 0.8 mm", unit="coil", price=(6_10_000_00, 8_60_000_00)),
    ],
}
# Deterministic defaults for manifest lines (manifest carries counts only).
CATEGORY_DEFAULT_ITEM = {"cartons": 1, "bagged_material": 0, "steel_coils": 0}
CATEGORY_DEFAULT_PRICE_PAISE = {"cartons": 55_000, "bagged_material": 95_000, "steel_coils": 6_40_000_00}
CATEGORY_VENDOR_CODE = {"cartons": "VND-001", "bagged_material": "VND-004", "steel_coils": "VND-003"}
VENDOR_CATEGORY = {"VND-001": "cartons", "VND-002": "bagged_material",
                   "VND-003": "steel_coils", "VND-004": "bagged_material"}
STOREKEEPERS = ["Ramesh Yadav", "Suresh Patil", "Anil Verma", "Kiran Jadhav"]
DRIVERS = ["Mohammed Rizwan", "Balwinder Singh", "Joseph D'Souza", "Prakash Nair"]


def catalog_line(category: str, item_index: int, qty: int, price_paise: int, tolerance_pct: float) -> PoLineSpec:
    spec = CATALOG[category][item_index]
    return PoLineSpec(category=category, sku=spec.sku, description=spec.description,
                      unit=spec.unit, qty=qty, price_paise=price_paise, tolerance_pct=tolerance_pct)


# The 8 document-only cases for PO-005..PO-012 (no video). `po_index` is the
# 0-based PO slot; exactly one of the modifier keys shapes the discrepancy.
DOCUMENT_CASES: list[DocumentCase] = [
    DocumentCase(po_index=4, type="invoice_price_above_po", vendor_code="VND-003",
                 lines=[("steel_coils", 0, 6, 6_40_000_00)], price_multiplier=1.08),
    DocumentCase(po_index=5, type="invoice_qty_exceeds_po", vendor_code="VND-001",
                 lines=[("cartons", 1, 100, 52_000)], qty_pct=112),
    DocumentCase(po_index=6, type="duplicate_invoice_number", vendor_code="VND-001",
                 lines=[("bagged_material", 0, 80, 98_000)], duplicates_po_index=0),
    DocumentCase(po_index=7, type="grn_short_beyond_tolerance", vendor_code="VND-002",
                 lines=[("bagged_material", 0, 100, 1_05_000)], grn_pct=94),
    DocumentCase(po_index=8, type="invoice_price_above_po", vendor_code="VND-003",
                 lines=[("steel_coils", 1, 8, 7_80_000_00)], price_multiplier=1.035),
    DocumentCase(po_index=9, type="invoice_qty_exceeds_grn", vendor_code="VND-003",
                 lines=[("steel_coils", 0, 20, 6_10_000_00)], grn_pct=90),
    DocumentCase(po_index=10, type="damaged_invoiced_in_full", vendor_code="VND-001",
                 lines=[("cartons", 0, 60, 24_000)], damaged=2),
    DocumentCase(po_index=11, type="invoice_qty_exceeds_po", vendor_code="VND-001",
                 lines=[("cartons", 2, 50, 36_000)], grn_pct=110, invoice_follows_grn=True),
]
