"""Seed contracts: manifest file shape, PO specs, expected verdicts, ground truth.

The manifest models use Pydantic aliases matching samples/scenarios/manifest.json
exactly (id, video, po, grn, invoice, true_count, true_damaged) with extra="forbid".
The manifest file's keys are never renamed; aliases map them to internal names.
"""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator

_CATEGORY_ALIASES = {
    "cartons": "cartons", "carton": "cartons", "boxes": "cartons",
    "bagged material": "bagged_material", "bagged_material": "bagged_material",
    "bags": "bagged_material",
    "steel coils": "steel_coils", "steel_coils": "steel_coils", "coils": "steel_coils",
}


def normalise_category(raw: str) -> str:
    try:
        return _CATEGORY_ALIASES[raw.strip().lower()]
    except KeyError:
        raise ValueError(f"manifest: unknown category {raw!r}") from None


class ManifestLine(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    category: str
    po_qty: int = Field(alias="po")
    grn_qty: int = Field(alias="grn")
    invoice_qty: int = Field(alias="invoice")
    truth_qty: int = Field(alias="true_count")
    truth_damaged: int = Field(alias="true_damaged")

    @field_validator("category", mode="before")
    @classmethod
    def _normalise_category(cls, value: object) -> object:
        return normalise_category(value) if isinstance(value, str) else value


class ManifestScenario(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    scenario_id: str = Field(alias="id")
    video: str  # filename only, exactly as in the manifest file
    lines: list[ManifestLine]

    @property
    def video_path(self) -> str:
        return f"samples/scenarios/{self.video}"


class ManifestFile(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    scenarios: list[ManifestScenario]


class EvalLine(BaseModel):
    """One line as evaluated in Python for an expected verdict."""

    category: str
    po_qty: int
    grn_qty: int
    grn_damaged: int = 0
    inv_qty: int
    po_price_paise: int
    inv_price_paise: int
    truth_qty: int | None = None
    truth_damaged: int = 0


class ExpectedLineResult(EvalLine):
    basis_qty: int
    damaged: int
    payable_qty: int
    variance_qty: int
    variance_pct: float
    price_variance_pct: float


class ExpectedResult(BaseModel):
    """Ground-truth outcome. Vocabulary is seed-local and independent of the
    runtime decision path: approve | partial_pay | hold_payment."""

    verdict: str
    policy_clauses: list[str] = []
    discrepancy_types: list[str] = []
    amount_at_risk_paise: int = 0
    requires_debit_note: bool = False
    debit_qty: int = 0
    per_line: list[ExpectedLineResult] = []


class PoLineSpec(BaseModel):
    category: str
    sku: str
    description: str
    unit: str
    qty: int
    price_paise: int
    tolerance_pct: float


class DocumentCase(BaseModel):
    po_index: int
    type: str
    vendor_code: str
    lines: list[tuple[str, int, int, int]]  # (category, catalog item, qty, price_paise)
    price_multiplier: float | None = None
    qty_pct: int | None = None
    grn_pct: int | None = None
    damaged: int = 0
    duplicates_po_index: int | None = None
    invoice_follows_grn: bool = False


class PoSpec(BaseModel):
    vendor_code: str
    scenario_id: str | None = None
    video: str | None = None
    lines: list[PoLineSpec] = []
    doc_case: DocumentCase | None = None
    eval_lines: list[EvalLine] = []
    verdict: ExpectedResult | None = None
    order_date: date | None = None
    expected_days: int = 7
    received_date: date | None = None
    vehicle_no: str = ""
    invoice_number: str = ""


class VendorSpec(BaseModel):
    code: str
    name: str
    gstin: str
    city: str
    state: str
    primary_category: str
    contact_name: str
    contact_email: str


class CatalogItem(BaseModel):
    sku: str
    description: str
    unit: str
    price: tuple[int, int]  # (min_paise, max_paise)


class ClauseRewrite(BaseModel):
    """BULK_MODEL output for one policy clause rewrite."""

    clause_id: str
    prose: str


class GroundTruthPoLine(BaseModel):
    qty: int
    unit: str
    category: str


class GroundTruthGrnLine(BaseModel):
    qty: int
    damaged: int


class GroundTruthInvoiceLine(BaseModel):
    qty: int
    unit_price_inr: float


class GroundTruthInvoice(BaseModel):
    number: str
    lines: list[GroundTruthInvoiceLine] = []
    total_paise: int


class GroundTruthDocuments(BaseModel):
    po: list[GroundTruthPoLine] = []
    grn: list[GroundTruthGrnLine] = []
    invoice: GroundTruthInvoice


class GroundTruthTruthLine(BaseModel):
    qty: int
    damaged: int
    unit: str


class GroundTruthVariance(BaseModel):
    qty: int
    pct: float


class GroundTruthCase(BaseModel):
    po_number: str
    scenario_id: str | None = None
    source: str
    video_path: str | None = None
    vendor: str
    documents: GroundTruthDocuments
    truth: list[GroundTruthTruthLine] | None = None
    discrepancy_types: list[str] = []
    seeded_type: str | None = None
    is_discrepancy: bool = False
    correct_verdict: str
    policy_clauses: list[str] = []
    variance: list[GroundTruthVariance] = []
    amount_at_risk_paise: int = 0
    amount_at_risk_inr: str = "₹0"
    requires_debit_note: bool = False
    debit_qty: int = 0
    note: str | None = None


class SeedTotals(BaseModel):
    po_value_paise: int = 0
    at_risk_paise: int = 0


class SeedResult(BaseModel):
    counts: dict[str, int]
    ground_truth: list[GroundTruthCase]
    totals: SeedTotals
    clean_count: int
    policy_verified: bool
    truth_changed: bool
