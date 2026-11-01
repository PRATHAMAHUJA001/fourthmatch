import type { CaseDetail, CaseSummary, PurchaseOrderDetail, PurchaseOrderRead, RuleRead } from "../types/api";

/** Fixtures mirror data/ground_truth.json scenarios. Synthetic only. */
export const purchaseOrders: PurchaseOrderDetail[] = [
  {
    id: 1, po_number: "FM/PO/26-27/001", vendor_id: 1, order_date: "2026-10-28", expected_date: "2026-11-02",
    status: "open", currency: "INR", total_paise: 778800, scenario_id: "scn1_clean", synthetic: true,
    lines: [{ id: 1, line_no: 1, category: "cartons", sku: "CTN-550", description: "Corrugated cartons 550 GSM", unit: "box", qty_ordered: 12, unit_price_paise: 55000, tolerance_pct: 0, line_total_paise: 660000 }],
  },
  {
    id: 2, po_number: "FM/PO/26-27/002", vendor_id: 1, order_date: "2026-10-28", expected_date: "2026-11-02",
    status: "open", currency: "INR", total_paise: 778800, scenario_id: "scn2_short", synthetic: true,
    lines: [{ id: 2, line_no: 1, category: "cartons", sku: "CTN-550", description: "Corrugated cartons 550 GSM", unit: "box", qty_ordered: 12, unit_price_paise: 55000, tolerance_pct: 0, line_total_paise: 660000 }],
  },
  {
    id: 5, po_number: "FM/PO/26-27/005", vendor_id: 3, order_date: "2026-10-29", expected_date: "2026-11-03",
    status: "open", currency: "INR", total_paise: 36249600, scenario_id: null, synthetic: true,
    lines: [{ id: 5, line_no: 1, category: "steel_coils", sku: "STL-HR-2T", description: "HR steel coils 2T", unit: "coil", qty_ordered: 8, unit_price_paise: 3840000, tolerance_pct: 0, line_total_paise: 30720000 }],
  },
  {
    id: 7, po_number: "FM/PO/26-27/007", vendor_id: 1, order_date: "2026-10-29", expected_date: "2026-11-03",
    status: "open", currency: "INR", total_paise: 9251200, scenario_id: null, synthetic: true,
    lines: [{ id: 7, line_no: 1, category: "cartons", sku: "CTN-550", description: "Corrugated cartons 550 GSM", unit: "box", qty_ordered: 120, unit_price_paise: 65333, tolerance_pct: 0, line_total_paise: 7840000 }],
  },
];

export const purchaseOrderReads: PurchaseOrderRead[] = purchaseOrders.map(({ lines: _l, ...rest }) => rest);

export const rules: RuleRead[] = [
  { id: 1, rule_id: "R-4.2-cartons", goods_category: "cartons", action: "hold", signoff_role: null, source_clause: "4.2", source_text: "Quantity variance beyond tolerance holds payment.", ambiguity: null, status: "approved", tolerance_pct: 0 },
  { id: 2, rule_id: "R-4.3-bagged", goods_category: "bagged_material", action: "partial_pay", signoff_role: null, source_clause: "4.3", source_text: "Bagged material tolerance 2%.", ambiguity: null, status: "pending_approval", tolerance_pct: 2 },
  { id: 3, rule_id: "R-5.1-price", goods_category: null, action: "hold", signoff_role: "purchase_manager", source_clause: "5.1", source_text: "Invoice price above PO by >2% requires sign-off.", ambiguity: null, status: "approved", tolerance_pct: 2 },
];

/** Case fixtures for MSW only. Synthetic; mirrors the seeded scenarios.
 * Real numbers come from GET /api/cases (computed in Python). */
export const caseDetails: CaseDetail[] = [
  {
    po_id: 1, po_number: "FM/PO/26-27/001", vendor_id: 1, vendor_name: "Acme Packaging Ltd",
    scenario_id: "scn1_clean", status: "received", order_date: "2026-10-28", expected_date: "2026-11-02",
    total_paise: 660000, verdict: "approve", held_paise: 0, at_risk_paise: 0,
    policy_version: "1.0", lines_evaluated: 1, lines_total: 1,
    delivery_id: 11, grn_number: "GRN-001", invoice_number: "INV-001",
    triggered_rule_ids: [], signoff_roles: [],
    lines: [{
      po_line_id: 1, line_no: 1, sku: "CTN-550", description: "Corrugated cartons 550 GSM",
      category: "cartons", unit: "box", po_qty: 12, grn_qty: 12, invoiced_qty: 12,
      observed_count: 12, damage_count: 0, evidence_source: "video", evidence_quality: "reliable",
      unit_price_paise: 55000, po_unit_price_paise: 55000, line_value_paise: 660000,
      variance_pct: 0, verdict: "approve", held_paise: 0, at_risk_paise: 0,
      signoff_roles: [], cited_rules: [],
    }],
  },
  {
    po_id: 2, po_number: "FM/PO/26-27/002", vendor_id: 1, vendor_name: "Acme Packaging Ltd",
    scenario_id: "scn2_short", status: "received", order_date: "2026-10-28", expected_date: "2026-11-02",
    total_paise: 660000, verdict: "partial_pay", held_paise: 165000, at_risk_paise: 165000,
    policy_version: "1.0", lines_evaluated: 1, lines_total: 1,
    delivery_id: 12, grn_number: "GRN-002", invoice_number: "INV-002",
    triggered_rule_ids: ["R-4.2-cartons"], signoff_roles: [],
    lines: [{
      po_line_id: 2, line_no: 1, sku: "CTN-550", description: "Corrugated cartons 550 GSM",
      category: "cartons", unit: "box", po_qty: 12, grn_qty: 9, invoiced_qty: 12,
      observed_count: 9, damage_count: 0, evidence_source: "video", evidence_quality: "reliable",
      unit_price_paise: 55000, po_unit_price_paise: 55000, line_value_paise: 660000,
      variance_pct: 25, verdict: "partial_pay", held_paise: 165000, at_risk_paise: 165000,
      signoff_roles: [],
      cited_rules: [{
        rule_id: "R-4.2-cartons", source_clause: "4.2",
        source_text: "Quantity variance beyond tolerance holds the disputed portion.",
        action: "partial_pay",
      }],
    }],
  },
  {
    po_id: 5, po_number: "FM/PO/26-27/005", vendor_id: 3, vendor_name: "Deccan Steel Traders",
    scenario_id: null, status: "received", order_date: "2026-10-29", expected_date: "2026-11-03",
    total_paise: 30720000, verdict: "human_review", held_paise: 30720000, at_risk_paise: 0,
    policy_version: "1.0", lines_evaluated: 1, lines_total: 1,
    delivery_id: 15, grn_number: "GRN-005", invoice_number: "INV-005",
    triggered_rule_ids: [], signoff_roles: [],
    lines: [{
      po_line_id: 5, line_no: 1, sku: "STL-HR-2T", description: "HR steel coils 2T",
      category: "steel_coils", unit: "coil", po_qty: 8, grn_qty: 8, invoiced_qty: 8,
      observed_count: 5, damage_count: 0, evidence_source: "video", evidence_quality: "insufficient",
      unit_price_paise: 3840000, po_unit_price_paise: 3840000, line_value_paise: 30720000,
      variance_pct: 37.5, verdict: "human_review", held_paise: 30720000, at_risk_paise: 0,
      signoff_roles: [], cited_rules: [],
    }],
  },
  {
    po_id: 7, po_number: "FM/PO/26-27/007", vendor_id: 1, vendor_name: "Acme Packaging Ltd",
    scenario_id: null, status: "received", order_date: "2026-10-29", expected_date: "2026-11-03",
    total_paise: 7840000, verdict: "partial_pay", held_paise: 653330, at_risk_paise: 653330,
    policy_version: "1.0", lines_evaluated: 1, lines_total: 1,
    delivery_id: null, grn_number: "GRN-007", invoice_number: "INV-007",
    triggered_rule_ids: ["R-4.2-cartons"], signoff_roles: [],
    lines: [{
      po_line_id: 7, line_no: 1, sku: "CTN-550", description: "Corrugated cartons 550 GSM",
      category: "cartons", unit: "box", po_qty: 120, grn_qty: 110, invoiced_qty: 120,
      observed_count: 110, damage_count: 0, evidence_source: "document", evidence_quality: null,
      unit_price_paise: 65333, po_unit_price_paise: 65333, line_value_paise: 7839960,
      variance_pct: 8.33, verdict: "partial_pay", held_paise: 653330, at_risk_paise: 653330,
      signoff_roles: [],
      cited_rules: [{
        rule_id: "R-4.2-cartons", source_clause: "4.2",
        source_text: "Quantity variance beyond tolerance holds the disputed portion.",
        action: "partial_pay",
      }],
    }],
  },
];

export const caseSummaries: CaseSummary[] = caseDetails;
