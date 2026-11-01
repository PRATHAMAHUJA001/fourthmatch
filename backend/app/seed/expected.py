"""Ground-truth expected verdicts: standalone, Python-only, policy numbers only
from app.seed.policy_template.POLICY.

This module is deliberately independent of the runtime decision path: it imports
nothing from app.domain.rules, app.services, or app.seed.verdict, and nothing in
services/ or domain/ may import it (enforced by tests/test_seed.py AST scans).
The LLM never does arithmetic; every number here is computed in Python.

Vocabulary (seed-local): approve | partial_pay | hold.
  approve      — no discrepancy beyond tolerance, no damage, no duplicate.
  partial_pay  — pay the undisputed payable quantity, hold the disputed portion
                 (short shipment beyond tolerance, damaged units invoiced,
                 invoice quantity above PO/GRN). Damage also requires a debit note.
  hold — hold the invoice in full (duplicate invoice, price beyond
                 tolerance, or nothing payable).
"""
from __future__ import annotations

from collections.abc import Sequence

from app.domain.schemas.seed import EvalLine, ExpectedLineResult, ExpectedResult
from app.seed.policy_template import POLICY

_CL_QTY = "4.2"
_CL_PRICE = "5.1"
_CL_INVOICE_OVER_PO = "5.2"
_CL_DUPLICATE = "5.3"
_CL_DAMAGE = "6.1"
_CL_VIDEO_PREVAILS = "8.4"


def expected_verdict(lines: Sequence[EvalLine], *, duplicate: bool = False) -> ExpectedResult:
    """Expected ground-truth verdict for one PO's lines, from POLICY tolerances."""
    clauses: list[str] = []
    types: list[str] = []
    at_risk = 0
    debit_qty = 0
    per_line: list[ExpectedLineResult] = []

    if duplicate:
        clauses.append(_CL_DUPLICATE)
        types.append("duplicate_invoice_number")

    payable_total = 0
    for ln in lines:
        basis_qty = ln.truth_qty if ln.truth_qty is not None else ln.grn_qty
        damaged = ln.truth_damaged if ln.truth_qty is not None else ln.grn_damaged
        damaged = min(max(damaged, 0), max(basis_qty, 0))
        payable_qty = min(max(basis_qty - damaged, 0), ln.po_qty)
        payable_total += payable_qty
        short = ln.po_qty - basis_qty
        var_pct = (short / ln.po_qty * 100) if ln.po_qty else 0.0
        tolerance_pct = float(POLICY["quantity_tolerance_pct"][ln.category])
        price_var_pct = (
            (ln.inv_price_paise - ln.po_price_paise) / ln.po_price_paise * 100
            if ln.po_price_paise
            else 0.0
        )
        line_risk = 0

        if ln.inv_qty > ln.po_qty:
            line_risk += (ln.inv_qty - ln.po_qty) * ln.inv_price_paise
            clauses.append(_CL_INVOICE_OVER_PO)
            types.append("invoice_qty_exceeds_po")
        if basis_qty < ln.po_qty and var_pct > tolerance_pct:
            line_risk += short * ln.po_price_paise
            clauses.append(_CL_QTY)
            types.append("short_shipment_beyond_tolerance")
        if price_var_pct > float(POLICY["price_tolerance_pct"]):
            line_risk += (ln.inv_price_paise - ln.po_price_paise) * ln.inv_qty
            clauses.append(_CL_PRICE)
            types.append("invoice_price_above_po")
        if damaged > 0 and ln.inv_qty > payable_qty:
            line_risk += damaged * ln.po_price_paise
            clauses.append(_CL_DAMAGE)
            types.append("damaged_units_invoiced")
            debit_qty += damaged
        if ln.truth_qty is not None and ln.grn_qty != ln.truth_qty:
            clauses.append(_CL_VIDEO_PREVAILS)
            types.append("grn_contradicted_by_video")

        per_line.append(
            ExpectedLineResult(
                **ln.model_dump(),
                basis_qty=basis_qty,
                damaged=damaged,
                payable_qty=payable_qty,
                variance_qty=short,
                variance_pct=round(var_pct, 2),
                price_variance_pct=round(price_var_pct, 2),
            )
        )
        at_risk += line_risk

    if duplicate:  # clause 5.3: hold 100% of the duplicate's value
        at_risk = sum(ln.inv_qty * ln.inv_price_paise for ln in lines)
    if not types:
        return ExpectedResult(verdict="approve", per_line=per_line)
    if duplicate or "invoice_price_above_po" in types or payable_total <= 0:
        verdict = "hold"
    else:
        verdict = "partial_pay"
    return ExpectedResult(
        verdict=verdict,
        policy_clauses=sorted(set(clauses)),
        discrepancy_types=sorted(set(types)),
        amount_at_risk_paise=at_risk,
        requires_debit_note=debit_qty > 0,
        debit_qty=debit_qty,
        per_line=per_line,
    )
