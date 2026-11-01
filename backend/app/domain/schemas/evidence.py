"""Evidence-pack contracts: the JSON document, stored-pack records, API reads.

The document is the single source for both the PDF rendering and the JSON
file; its canonical bytes are what the pack SHA-256 covers. All amounts are
integer paise with a Python-formatted Indian display string beside them.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.domain.enums import Verdict

SCHEMA_VERSION = "1.0"
SYNTHETIC_BANNER = (
    "SYNTHETIC DATA - NOT A REAL TRANSACTION. Vendors, documents, footage and amounts in this "
    "pack are generated for demonstration; no real organisation, person or payment is involved."
)


class PackModels(BaseModel):
    """Model IDs in use, copied from config at build time (never hardcoded)."""

    perception_model: str = ""
    decision_model: str = ""
    compiler_model: str = ""
    seg_model: str = ""


class CaseSection(BaseModel):
    po_id: int
    po_number: str
    vendor_name: str
    scenario_id: str | None = None
    status: str
    order_date: date
    expected_date: date
    delivery_id: int
    grn_number: str | None = None
    invoice_number: str | None = None
    policy_version: str | None = None
    lines_evaluated: int
    lines_total: int
    po_total_paise: int
    po_total_display: str


class FourMatchRow(BaseModel):
    """One PO line across the four sources: PO | GRN | Invoice | Vision."""

    line_no: int
    sku: str
    description: str
    unit: str
    po_qty: int
    grn_qty: int | None = None
    invoiced_qty: int
    vision_count: int | None = None
    vision_source: str  # "video" | "document" | "none"
    evidence_quality: str | None = None
    damage_count: int = 0
    unit_price_paise: int
    unit_price_display: str
    variance_pct: float | None = None
    verdict: Verdict | None = None
    held_paise: int = 0
    held_display: str = "₹0"
    contradicts_grn: bool = False  # video count differs from the signed GRN quantity


class CitedClause(BaseModel):
    rule_id: str
    clause_id: str
    clause_text: str
    clause_source: Literal["policy_document", "compiled_rule"]
    action: str
    line_nos: list[int] = Field(default_factory=list)


class EvidenceFrame(BaseModel):
    index: int  # 1-based position in the pack
    label: str
    filename: str  # relative to the pack directory
    sha256: str
    source: Literal["overlay", "video_frame"]
    frame_index: int | None = None
    t_seconds: float | None = None


class TraceStep(BaseModel):
    seq: int
    tool: str
    detail: str


class AgentTraceSummary(BaseModel):
    recorded: bool
    decision_id: int | None = None
    verdict: str | None = None
    reason: str | None = None
    decided_by: str | None = None
    decided_at: datetime | None = None
    model: str | None = None
    summary: str | None = None
    recommended_action: str | None = None
    steps: list[TraceStep] = Field(default_factory=list)
    note: str = ""


class DebitLine(BaseModel):
    line_no: int
    description: str
    unit: str
    qty: int | None = None  # whole units when the amount divides evenly, else None
    unit_price_paise: int
    amount_paise: int
    amount_display: str
    reason: str
    clauses: list[str] = Field(default_factory=list)


class DebitNoteSection(BaseModel):
    number: str
    issue_date: date
    vendor_name: str
    po_number: str
    invoice_number: str | None = None
    lines: list[DebitLine]
    total_paise: int
    total_display: str


class EvidencePackDocument(BaseModel):
    schema_version: str = SCHEMA_VERSION
    synthetic: bool = True
    synthetic_banner: str = SYNTHETIC_BANNER
    generated_at: datetime
    case: CaseSection
    verdict: Verdict
    amount_held_paise: int
    amount_held_display: str
    at_risk_paise: int
    at_risk_display: str
    signoff_roles: list[str] = Field(default_factory=list)
    four_match: list[FourMatchRow]
    cited_clauses: list[CitedClause]
    frames: list[EvidenceFrame] = Field(default_factory=list)
    frames_note: str = ""
    video_sha256: str | None = None
    agent_trace: AgentTraceSummary
    models: PackModels
    debit_note: DebitNoteSection | None = None
    numbers_note: str = "All counts, variances and amounts are computed in Python from stored records; models perform no arithmetic."


# ----------------------------------------------------------- stored / API


class ManifestEntry(BaseModel):
    name: str  # evidence_pack.pdf | evidence_pack.json | debit_note.pdf | frames/frame_1.jpg
    path: str  # relative to storage root
    sha256: str
    bytes: int
    role: Literal["pdf", "json", "debit_note", "frame"]


class StoredPack(BaseModel):
    id: int
    po_id: int
    delivery_id: int | None = None
    decision_id: int | None = None
    sha256: str
    verified: bool
    created_at: datetime
    pdf_path: str | None = None
    json_path: str | None = None
    manifest: list[ManifestEntry] = Field(default_factory=list)


class NewPack(BaseModel):
    po_id: int
    delivery_id: int
    decision_id: int | None = None
    sha256: str
    pdf_path: str
    json_path: str
    verified: bool
    manifest: list[ManifestEntry]


class EvidencePackRead(BaseModel):
    sha256: str
    created_at: datetime
    verified: bool
    files: list[str]


class EvidenceFile(BaseModel):
    name: str
    media_type: str
    data: bytes


class DeliveryRef(BaseModel):
    id: int
    po_id: int
    video_path: str | None = None


class DecisionSnapshot(BaseModel):
    """What the pack needs from a stored Decision row (all optional fields tolerated)."""

    id: int
    verdict: str
    reason: str
    decided_by: str
    created_at: datetime
    model: str | None = None
    summary: str | None = None
    recommended_action: str | None = None
    trace: list[TraceStep] = Field(default_factory=list)


class FrameImage(BaseModel):
    label: str
    source: Literal["overlay", "video_frame"]
    frame_index: int | None = None
    t_seconds: float | None = None
    jpeg: bytes


class FrameCollection(BaseModel):
    frames: list[FrameImage] = Field(default_factory=list)
    video_sha256: str | None = None
    note: str = ""
