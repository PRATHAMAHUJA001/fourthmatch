"""Receiving policy template: the single source of truth for the policy.

Every clause number and every number in data/policy/receiving_policy.md lives
here. The markdown is *checked against this template in Python*: each clause's
numbers (rupee amounts, percentages, day counts, confidence) are extracted and
compared; a clause that is missing or whose numbers differ is regenerated from
the canonical text below. Matching clauses keep their existing prose.

Changing a number here changes: PO line tolerances, the rules table, ground
truth verdicts, and (on next seed) the policy document. No LLM is involved.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.domain.money import format_inr

POLICY_VERSION = "1.0"
POLICY_EFFECTIVE = "2026-04-01"
COMPANY = "FourthMatch Manufacturing Pvt. Ltd."  # synthetic company, synthetic policy
DOCUMENT_NO = "FM-POL-PROC-001"

POLICY: dict = {
    "policy_version": POLICY_VERSION,
    "effective_date": POLICY_EFFECTIVE,
    "quantity_tolerance_pct": {  # clause 4.2
        "cartons": 0.0,
        "bagged_material": 2.0,
        "steel_coils": 0.0,
    },
    "price_tolerance_pct": 2.0,            # clause 5.1
    "invoice_over_po_tolerance_pct": 0.0,  # clause 5.2
    "duplicate_hold_pct": 100.0,           # clause 5.3
    "damage_debit_pct": 100.0,             # clause 6.1
    "damaged_units_payable": 0,            # clause 6.1
    "payment_terms_days": 30,              # clause 7.1
    "hold_notice_working_days": 3,         # clause 7.2
    "debit_note_working_days": 7,          # clause 6.3
    "qa_disposition_working_days": 5,      # clause 6.2
    "evidence_retention_years": 7,         # clause 9.1
    "min_track_confidence": 0.80,          # clause 8.2
    "approval_limits_paise": {             # clauses 3.3-3.5
        "stores_manager_up_to_paise": 100_000_00,    # ₹1,00,000
        "purchase_manager_up_to_paise": 500_000_00,  # ₹5,00,000
    },
}

# Clause IDs relied on by code (verdicts, rules) — defined once, here.
CL_QTY_TOLERANCE = "4.2"
CL_PRICE = "5.1"
CL_INVOICE_OVER_PO = "5.2"
CL_DUPLICATE = "5.3"
CL_DAMAGE = "6.1"
CL_WEAK_EVIDENCE = "8.3"
CL_VIDEO_PREVAILS = "8.4"

CATEGORIES = ("cartons", "bagged_material", "steel_coils")
SECTIONS = [(1, "Purpose"), (2, "Definitions"), (3, "Roles and sign-off"),
            (4, "Quantity verification"), (5, "Invoice verification"),
            (6, "Damage and debit notes"), (7, "Payment and payment holds"),
            (8, "Evidence"), (9, "Records and review")]


@dataclass(frozen=True)
class Clause:
    id: str
    text: str  # canonical prose, rendered from POLICY
    numbers: dict[str, float] = field(default_factory=dict)  # semantic name -> value

    @property
    def section(self) -> int:
        return int(self.id.split(".")[0])

    @property
    def number_set(self) -> set[float]:
        return {float(v) for v in self.numbers.values()}


def _clauses() -> list[Clause]:
    p, qt = POLICY, POLICY["quantity_tolerance_pct"]
    stores = format_inr(p["approval_limits_paise"]["stores_manager_up_to_paise"])
    purchase = format_inr(p["approval_limits_paise"]["purchase_manager_up_to_paise"])
    C = Clause
    return [
        C("1.1", "This Policy establishes the standard for receipt, verification, documentation and payment control for materials received at plant stores against approved Purchase Orders."),
        C("1.2", "This Policy applies to all plant stores receipts, including raw materials, packing materials, cartons, bagged material and steel coils, and to all related invoices, debit notes and payment holds."),
        C("1.3", "This Policy ensures that stock records reflect only verified and acceptable material, and that payment is released only for such material in line with agreed terms and approvals."),
        C("1.4", "All personnel engaged in indenting, purchasing, stores receipt, quality inspection, and finance booking and payment shall comply with this Policy."),
        C("2.1", "Purchase Order means the approved order placed on a supplier stating material, quantity, price and delivery terms."),
        C("2.2", "Goods Receipt Note means the stores record confirming material received, verified quantity, and damage or shortage where observed."),
        C("2.3", "Damage means breakage, leakage, rust, deformation, contamination, wetting or any condition rendering material unfit for intended use, as confirmed by Quality Assurance."),
        C("2.4", "Debit Note means the written claim issued to a supplier to recover value for damage, shortage, rejection or price correction."),
        C("2.5", "Hold means the documented status preventing booking or payment of an invoice or portion thereof until stated conditions are cleared."),
        C("2.6", "Evidence means photographs, video recordings, weighment slips, count sheets, inspection reports and system tracking logs linked to a Goods Receipt Note."),
        C("2.7", "Supplier means the party named in the Purchase Order as the seller and issuer of the invoice."),
        C("2.8", "Finance Controller means the head of plant finance responsible for booking, hold control and payment release jointly with Purchase as stated herein."),
        C("3.1", "The Storekeeper shall supervise unloading, verify count and weighment, record findings truthfully, and sign the Goods Receipt Note to confirm the receipt as recorded."),
        C("3.2", "Where shortage, excess or damage is observed, Quality Assurance shall inspect the consignment and shall co-sign the Goods Receipt Note and the damage record to confirm findings and disposition pending details."),
        C("3.3", f"The Stores Manager shall approve Goods Receipt Notes and invoices with invoice value up to {stores}.",
          {"stores_manager_limit_rupees": 100_000.0}),
        C("3.4", f"The Purchase Manager shall approve Goods Receipt Notes and invoices with invoice value up to {purchase}.",
          {"purchase_manager_limit_rupees": 500_000.0}),
        C("3.5", f"The Plant Head shall approve Goods Receipt Notes and invoices with invoice value above {purchase}.",
          {"purchase_manager_limit_rupees": 500_000.0}),
        C("3.6", "Payment holds imposed under this Policy shall be released jointly by the Purchase Manager and the Finance Controller after due verification and recording of clearance."),
        C("3.7", "No person shall approve a receipt, invoice or hold release where a conflict of interest exists, and such cases shall be escalated to higher authority for decision."),
        C("3.8", "Stores and Finance shall ensure that personnel handling receipts, inspection and payment are trained in this Policy and in correct documentation."),
        C("4.1", "Quantity shall be verified at the time of unloading against the Purchase Order and the supplier challan, using count for countable units and weighment where applicable, and combined methods where required by Purchase."),
        C("4.2", f"Quantity tolerance for acceptance without escalation shall be as follows: cartons at {qt['cartons']:.1f}%, bagged material at {qt['bagged_material']:.1f}%, and steel coils at {qt['steel_coils']:.1f}%. Shortage beyond the applicable tolerance shall require review and approval by the Stores Manager before closure of the Goods Receipt Note. Payment shall be released only for the quantity received within tolerance, and the value of the shortfall beyond tolerance shall be withheld pending that Stores Manager review.",
          {"cartons_tolerance_pct": qt["cartons"], "bagged_material_tolerance_pct": qt["bagged_material"],
           "steel_coils_tolerance_pct": qt["steel_coils"]}),
        C("4.3", "Weighment slips, count sheets and supporting photographs of vehicle, unloading, stacking and shortage or excess shall be attached to the Goods Receipt Note."),
        C("4.4", "Excess quantity that is not required or not approved shall be segregated in a marked hold area, shall not be taken into usable stock, and shall be returned to the supplier or regularised through a Purchase Order amendment before use."),
        C("4.5", "Short quantity against the Purchase Order shall be recorded as short receipt, and the Goods Receipt Note shall reflect only the quantity actually received in acceptable condition."),
        C("4.6", "The Goods Receipt Note shall be prepared on the same shift as unloading wherever feasible and shall state vehicle details, challan details and verification method for traceability."),
        C("5.1", f"Invoice price shall be matched to the Purchase Order price, and variation up to {p['price_tolerance_pct']:.1f}% may be accepted with approval as per sign-off limits, while variation beyond the stated tolerance shall be held for Purchase clarification and Purchase Order price correction before booking.",
          {"price_tolerance_pct": p["price_tolerance_pct"]}),
        C("5.2", f"Invoiced quantity shall be matched to the Purchase Order quantity and the Goods Receipt Note quantity, and tolerance for invoiced quantity above Purchase Order quantity shall be {p['invoice_over_po_tolerance_pct']:.1f}%. Any invoiced quantity above Purchase Order quantity shall be held and shall not be paid until the Purchase Order is duly amended and approved.",
          {"invoice_over_po_tolerance_pct": p["invoice_over_po_tolerance_pct"]}),
        C("5.3", f"Any invoice bearing the same supplier and supplier invoice number as an invoice already booked shall be treated as a duplicate invoice, shall not be booked again, and payment on it shall be held at {p['duplicate_hold_pct']:.1f}% of its value until the supplier proves it is not a second presentation of the same supply.",
          {"duplicate_hold_pct": p["duplicate_hold_pct"]}),
        C("5.4", "Supplier name, tax particulars, Purchase Order reference and Goods Receipt Note reference shall be verified before booking, and invoices with material mismatch in these particulars shall be held until corrected by the supplier through a compliant document."),
        C("5.5", "Credit notes received from suppliers against shortage, damage or price correction shall be linked to the related invoice and debit note and shall be adjusted before payment release."),
        C("6.1", f"Damaged units identified at receipt or during inspection shall be recorded separately and shall not be taken into usable stock, and the payable quantity for damaged units shall be {p['damaged_units_payable']}. Debit for damaged units shall be raised at {p['damage_debit_pct']:.1f}% of the value of such units at the Purchase Order unit price.",
          {"damaged_units_payable": float(p["damaged_units_payable"]), "damage_debit_pct": p["damage_debit_pct"]}),
        C("6.2", f"Quality Assurance shall complete inspection and issue written disposition for damaged, short or rejected material within {p['qa_disposition_working_days']} working days of recording in the Goods Receipt Note, specifying acceptance, rejection, segregation, return or disposal as applicable.",
          {"qa_disposition_working_days": float(p["qa_disposition_working_days"])}),
        C("6.3", f"Purchase shall issue the debit note to the supplier within {p['debit_note_working_days']} working days of the Goods Receipt Note, and Finance shall adjust the debit note against the supplier account before release of related payment.",
          {"debit_note_working_days": float(p["debit_note_working_days"])}),
        C("6.4", "Damaged and rejected material pending return or disposal shall remain segregated under store custody with clear identification and shall be dispatched or disposed of only after documented authorisation."),
        C("6.5", "Where damage appears to arise during transit, Purchase shall lodge a claim with the transporter in addition to the supplier debit, and photographic and video evidence shall support such claim."),
        C("7.1", f"Standard payment terms shall be {p['payment_terms_days']} days from booking of a complete, matched and approved invoice with Goods Receipt Note, subject to holds under this Policy. Invoices that are incomplete, mismatched or under hold shall not be treated as due until defects are cured and approval is complete.",
          {"payment_terms_days": float(p["payment_terms_days"])}),
        C("7.2", f"Finance shall place payment on hold where quantity, price, damage, duplicate invoice or evidence requirements are not met, and shall intimate Purchase and the supplier within {p['hold_notice_working_days']} working days of identification of the hold, stating reasons for hold and documents required for release.",
          {"hold_notice_working_days": float(p["hold_notice_working_days"])}),
        C("7.3", "Holds shall be released jointly by the Purchase Manager and the Finance Controller only after the underlying mismatch is corrected, damage is settled through debit note, or required approval and evidence are completed and duly recorded."),
        C("7.4", "Release may be allowed for the undisputed and accepted portion of an invoice that is fully matched, documented and approved, while the disputed portion shall remain on hold until final resolution and documented closure."),
        C("7.5", "No payment shall be released for held invoices through advances or adjustments that bypass hold controls, and any exception shall require written justification with joint approval and full audit trail."),
        C("8.1", "Unloading, counting, weighment and inspection of consignments shall be supported by continuous video evidence showing vehicle, material, handling and recording activity, and such recordings shall be linked to the Goods Receipt Note and preserved for audit and review. Where dock video exists, the counted units are the unique object tracks counted from that video."),
        C("8.2", f"Where automated video tracking is used to support quantity or damage verification, only tracks with confidence at or above {p['min_track_confidence']:.2f} shall be relied upon as system evidence, and settings and logs for such tracking shall be retained with the Goods Receipt Note.",
          {"min_track_confidence": p["min_track_confidence"]}),
        C("8.3", "Where video evidence is missing, incomplete or assessed below the confidence stated in this Policy, the matter shall be routed to human review with manual recount or reweighment and independent verification, and payment for the affected portion shall remain on hold until human review is complete and approved. Weak evidence is never a basis to approve."),
        C("8.4", "A Goods Receipt Note signed by the storekeeper is a receiving record, not proof against contradictory video: where video and the Goods Receipt Note disagree, the video count prevails for payment and the Goods Receipt Note shall be corrected by a signed amendment."),
        C("8.5", "Storage and retrieval of video evidence shall preserve integrity and prevent alteration, with access restricted to authorised personnel and viewing logged for audit. An evidence pack (documents, counts, decision and the clauses relied on) shall be generated for every held or reviewed delivery and hash-sealed so it can be re-verified later."),
        C("9.1", f"Purchase Orders, Goods Receipt Notes, invoices, debit notes, inspection and disposition records, hold and release records, and video evidence and tracking logs shall be preserved and retrievable for audit for {p['evidence_retention_years']} years.",
          {"evidence_retention_years": float(p["evidence_retention_years"])}),
        C("9.2", "Stores, Purchase, Quality Assurance and Finance shall review holds, debit notes and evidence gaps from time to time, and shall initiate corrective action with suppliers, transporters and internal teams to prevent recurrence."),
        C("9.3", "This Policy shall be reviewed from time to time for continued suitability, and amendments shall be approved and communicated before implementation, with training provided to concerned personnel. Tolerances may be changed only by a new numbered version of this document."),
        C("9.4", "Non-compliance with this Policy shall be reported through the defined escalation path and shall be addressed through corrective action, retraining or disciplinary measures as applicable under Company rules."),
    ]


CLAUSES: list[Clause] = _clauses()
CLAUSE_BY_ID: dict[str, Clause] = {c.id: c for c in CLAUSES}

RULE_SPECS: list[dict] = [
    *[{"clause": CL_QTY_TOLERANCE, "category": cat, "rule_type": "quantity_tolerance",
       "threshold_pct": POLICY["quantity_tolerance_pct"][cat], "action": "hold",
       "description": f"Received qty vs PO qty tolerance for {cat} is {POLICY['quantity_tolerance_pct'][cat]:.1f}%; shortage beyond it holds payment."}
      for cat in CATEGORIES],
    {"clause": CL_PRICE, "category": None, "rule_type": "price_variance",
     "threshold_pct": POLICY["price_tolerance_pct"], "action": "hold",
     "description": "Invoice unit price may exceed PO unit price by at most the price tolerance; excess holds payment."},
    {"clause": CL_INVOICE_OVER_PO, "category": None, "rule_type": "invoice_qty_exceeds_po",
     "threshold_pct": POLICY["invoice_over_po_tolerance_pct"], "action": "hold",
     "description": "Quantity invoiced above the PO quantity is never payable; the excess holds payment."},
    {"clause": CL_DUPLICATE, "category": None, "rule_type": "duplicate_invoice",
     "threshold_pct": POLICY["duplicate_hold_pct"], "action": "hold",
     "description": "An invoice number already presented is a duplicate: hold its full value until the vendor proves otherwise."},
    {"clause": CL_DAMAGE, "category": None, "rule_type": "damage",
     "threshold_pct": POLICY["damage_debit_pct"], "action": "hold",
     "description": "Damaged units are not payable; debit their full PO-price value and hold until QA disposition."},
    {"clause": CL_WEAK_EVIDENCE, "category": None, "rule_type": "weak_evidence",
     "threshold_pct": POLICY["min_track_confidence"], "action": "human_review",
     "description": "Video/track evidence below the confidence threshold, missing, or contradictory is weak: human review, never approve."},
    {"clause": CL_VIDEO_PREVAILS, "category": None, "rule_type": "video_prevails_over_grn",
     "threshold_pct": None, "action": "hold",
     "description": "Where video and GRN disagree, the video count prevails for payment and the GRN is amended."},
]

# ---------------------------------------------------------------- rendering
_HEADER = f"""# Receiving and Payment-Hold Policy

**{COMPANY}**
**Document No. {DOCUMENT_NO}**
**Version {POLICY_VERSION}**
**Effective Date: {POLICY_EFFECTIVE}**
"""


def render_policy() -> str:
    """Full canonical policy markdown, entirely from this template."""
    return render_policy_with({})


def render_policy_with(prose_by_id: dict[str, str]) -> str:
    """Render the policy using rewritten prose where supplied (generator only).

    Clauses absent from prose_by_id keep their canonical template text. The
    seed loader never calls this — it only verifies the committed file.
    """
    parts = [_HEADER]
    for num, title in SECTIONS:
        parts.append(f"\n## {num} {title}\n")
        for clause in CLAUSES:
            if clause.section == num:
                parts.append(f"\n**{clause.id}** {prose_by_id.get(clause.id, clause.text)}\n")
    return "".join(parts)


# ---------------------------------------------------------------- checking
_AMOUNT_RE = re.compile(r"₹\s*([\d,]+(?:\.\d+)?)")
_NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?%?")
_CLAUSE_RE = re.compile(r"\*\*(\d+\.\d+)\*\*\s*(.*?)(?=\n\*\*\d+\.\d+\*\*|\n## |\Z)", re.S)


def extract_numbers(clause_text: str) -> set[float]:
    """All numbers in a clause's prose, normalised (₹1,00,000 -> 100000.0)."""
    found: set[float] = set()
    rest = _AMOUNT_RE.sub(lambda m: _add(found, m.group(1)), clause_text)
    for tok in _NUM_RE.findall(rest):
        _add(found, tok)
    return found


def _add(found: set[float], raw: str) -> str:
    try:
        found.add(float(raw.replace(",", "").rstrip("%")))
    except ValueError:
        pass
    return " "


def parse_clauses(md_text: str) -> dict[str, str]:
    return {m.group(1): m.group(2).strip() for m in _CLAUSE_RE.finditer(md_text)}


@dataclass
class PolicyCheck:
    mismatched: list[str]  # clause ids whose numbers differ from the template
    missing: list[str]
    header_ok: bool

    @property
    def ok(self) -> bool:
        return not self.mismatched and not self.missing and self.header_ok


def check_policy(md_text: str) -> PolicyCheck:
    """Compare every clause's numbers in the markdown against the template."""
    found = parse_clauses(md_text)
    mismatched, missing = [], []
    for clause in CLAUSES:
        if clause.id not in found:
            missing.append(clause.id)
        elif extract_numbers(found[clause.id]) != clause.number_set:
            mismatched.append(clause.id)
    header_ok = f"Version {POLICY_VERSION}" in md_text and POLICY_EFFECTIVE in md_text
    return PolicyCheck(mismatched=mismatched, missing=missing, header_ok=header_ok)
