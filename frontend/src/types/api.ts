/** Wire types mirroring backend Pydantic schemas. Paise everywhere. */

export type Verdict = "approve" | "partial_pay" | "hold" | "human_review";
export type EvidenceQuality = "reliable" | "insufficient";
export type JobStatus =
  | "queued" | "uploading" | "understanding" | "tracking" | "damage_check" | "done" | "failed";
export type RuleAction = "approve" | "partial_pay" | "hold" | "require_signoff";

export interface ApiErrorBody {
  error: { code: string; message: string; request_id: string };
}

export interface PoLineRead {
  id: number; line_no: number; category: string; sku: string;
  description: string; unit: string; qty_ordered: number;
  unit_price_paise: number; tolerance_pct: number; line_total_paise: number;
}

export interface PurchaseOrderRead {
  id: number; po_number: string; vendor_id: number;
  order_date: string; expected_date: string; status: string;
  currency: string; total_paise: number; scenario_id: string | null; synthetic: boolean;
}

export interface PurchaseOrderDetail extends PurchaseOrderRead {
  lines: PoLineRead[];
}

export interface DeliveryCreated { delivery_id: number; job_id: string; }

export interface JobEventRead {
  id: number; job_id: string; seq: number; event_type: string;
  message: string; payload: Record<string, unknown>; created_at: string;
}

export interface RuleRead {
  id: number; rule_id: string | null; goods_category: string | null;
  action: string; signoff_role: string | null; source_clause: string;
  source_text: string | null; ambiguity: string | null; status: string;
  tolerance_pct: number | null;
}

export interface HealthRead { status: string; }

export interface CitedRule {
  rule_id: string; source_clause: string; source_text: string; action: string;
}

export interface CaseLineRead {
  po_line_id: number; line_no: number; sku: string; description: string;
  category: string; unit: string;
  po_qty: number; grn_qty: number | null; invoiced_qty: number;
  observed_count: number | null; damage_count: number;
  evidence_source: "video" | "document" | "none";
  evidence_quality: EvidenceQuality | null;
  unit_price_paise: number; po_unit_price_paise: number; line_value_paise: number;
  variance_pct: number | null;
  verdict: Verdict | null; held_paise: number; at_risk_paise: number;
  signoff_roles: string[]; cited_rules: CitedRule[];
}

export interface CaseSummary {
  po_id: number; po_number: string; vendor_id: number; vendor_name: string;
  scenario_id: string | null; status: string;
  order_date: string; expected_date: string; total_paise: number;
  verdict: Verdict | null; held_paise: number; at_risk_paise: number;
  policy_version: string | null; lines_evaluated: number; lines_total: number;
}

export interface CaseDetail extends CaseSummary {
  delivery_id: number | null; grn_number: string | null; invoice_number: string | null;
  triggered_rule_ids: string[]; signoff_roles: string[];
  lines: CaseLineRead[];
}

export const VERDICT_LABEL: Record<Verdict, string> = {
  approve: "Verified",
  partial_pay: "Partial pay",
  hold: "On hold",
  human_review: "Needs review",
};
