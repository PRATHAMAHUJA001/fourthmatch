/** Wire types mirroring backend Pydantic schemas. Money is integer paise everywhere.
 *  Types marked "frontend contract" describe endpoints the backend will serve next
 *  (decision agent, analytics, eval); MSW serves them today from repo data files. */

export type Verdict = "approve" | "partial_pay" | "hold" | "human_review";
export type EvidenceQuality = "reliable" | "insufficient";
export type JobStatus =
  | "queued" | "uploading" | "transcribing_remark" | "understanding" | "tracking" | "damage_check"
  | "reconciling" | "applying_policy" | "verdict" | "done" | "failed";
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
  id: number; po_number: string; vendor_id: number; vendor_name?: string;
  order_date: string; expected_date: string; status: string;
  currency: string; total_paise: number; scenario_id: string | null; synthetic: boolean;
}

export interface PurchaseOrderDetail extends PurchaseOrderRead {
  lines: PoLineRead[];
}

export interface DeliveryCreated { delivery_id: number; job_id: string; po_id?: number }

export interface JobEventRead {
  id: number; job_id: string; seq: number; event_type: string;
  message: string; payload: Record<string, unknown>; created_at: string;
}

export interface RuleRead {
  id: number; rule_id: string | null; goods_category: string | null;
  action: string; signoff_role: string | null; source_clause: string;
  source_text: string | null; ambiguity: string | null; status: string;
  tolerance_pct: number | null;
  condition?: { field: string; op: string; value: number | string | boolean | null } | null;
}

export interface HealthRead { status: string }

export interface CitedRule {
  rule_id: string; source_clause: string; source_text: string; action: string;
}

/** Frontend contract: perception detail per line (from perception_results). */
export interface PerceptionRead {
  noun_phrase: string;
  observed_count: number;
  max_visible: number;
  track_ids: string[];
  damaged_track_ids: string[];
  reasons: string[];
  footage_needed: string | null;
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
  perception?: PerceptionRead | null;
}

export interface CaseSummary {
  po_id: number; po_number: string; vendor_id: number; vendor_name: string;
  scenario_id: string | null; status: string;
  order_date: string; expected_date: string; total_paise: number;
  verdict: Verdict | null; held_paise: number; at_risk_paise: number;
  policy_version: string | null; lines_evaluated: number; lines_total: number;
  discrepancy_types?: string[];
  clauses?: string[];
  evidence_source?: "video" | "document" | "none";
  decided_at?: string | null;
}

/** Frontend contract: decision agent output + trace. */
export interface AgentStep {
  seq: number;
  tool: string;
  args: Record<string, unknown>;
  result: Record<string, unknown>;
  latency_ms: number | null;
}

export interface DecisionRead {
  verdict: Verdict;
  amount_held_paise: number;
  summary_en: string;
  recommended_action: string;
  model: string;
  trace: AgentStep[];
}

export interface EvidencePackRead {
  sha256: string;
  created_at: string;
  verified: boolean;
  files: string[];
}

export interface CaseDetail extends CaseSummary {
  delivery_id: number | null; grn_number: string | null; invoice_number: string | null;
  triggered_rule_ids: string[]; signoff_roles: string[];
  lines: CaseLineRead[];
  video_url?: string | null;
  decision?: DecisionRead | null;
  evidence_pack?: EvidencePackRead | null;
  invoice_total_paise?: number | null;
  /** Storekeeper voice remark: context, never evidence. */
  remark?: RemarkRead | null;
}

export type RemarkStatus = "supported" | "not_supported" | "no_claim" | "unverifiable";
export type ClaimVerdict = "supported" | "not_supported" | "unverifiable";
export interface RemarkClaim { kind: "count" | "damage" | "other"; category: string | null; quantity: number | null; text: string }
export interface RemarkItem { claim: RemarkClaim; verdict: ClaimVerdict; observed: number | null }
export interface RemarkCheck { status: RemarkStatus; items: RemarkItem[] }
export interface RemarkRead { transcript: string; check: RemarkCheck | null }

/** Frontend contract: Dock Live. */
export interface DockKpis {
  held_today_paise: number;
  deliveries_verified: number;
  deliveries_total: number;
  discrepancy_rate_pct: number;
  avg_time_to_verdict_s: number | null;
}

/** Frontend contract: Policy. */
export interface PolicyClause { clause_id: string; section: string; text: string }
export interface PolicyRead {
  id: number; version: string; title: string; document_no: string;
  effective_date: string; clauses: PolicyClause[];
}
export interface SimulationDiff {
  po_number: string; vendor_name: string;
  before: Verdict | null; after: Verdict | null;
  held_before_paise: number; held_after_paise: number;
}
export interface SimulationRead {
  draft_policy_version: string;
  changed: SimulationDiff[];
  unchanged_count: number;
  held_before_paise: number;
  held_after_paise: number;
}

/** Frontend contract: Analytics. */
export interface AnalyticsRead {
  held_by_vendor: { vendor_name: string; held_paise: number; cases: number }[];
  trend: { date: string; deliveries: number; discrepancies: number }[];
  type_mix: { type: string; count: number }[];
  vendor_risk: { vendor_name: string; cases: number; discrepancies: number; held_paise: number; risk_score: number }[];
}

/** Frontend contract: Eval. */
export interface EvalCountRow {
  scenario: string; category: string; noun_phrase: string;
  true_count: number; observed_count: number; max_visible: number;
  evidence_quality: EvidenceQuality; true_damaged: number; flagged_damaged: number;
  result: "PASS" | "FAIL";
}
export interface EvalRead {
  verdict_metrics: { label: Verdict; precision: number | null; recall: number | null; f1: number | null; support: number }[];
  confusion: { labels: Verdict[]; matrix: number[][] };
  counts: EvalCountRow[];
  latency: { model: string; role: string; calls: number; p50_ms: number | null; p95_ms: number | null }[];
  cases_total: number;
  verdict_accuracy: number;
  count_accuracy: number;
  /** data/eval_results.json (scripts/run_eval.py); null until that has been run. */
  results: EvalResults | null;
}

/** data/eval_results.json. A value that was not measured is null; `not_measured` says why. */
export interface CountSummary {
  n: number; measured: number; correct: number; accuracy: number | null; mean_abs_error: number | null;
}
export interface ClassMetric { label: Verdict; precision: number | null; recall: number | null; f1: number | null; support: number }
export interface VerdictScore {
  source: "served" | "agent";
  cases_total: number; cases_correct: number; accuracy: number | null;
  per_class: ClassMetric[];
  macro_precision: number | null; macro_recall: number | null; macro_f1: number | null;
  confusion: { labels: Verdict[]; matrix: number[][] };
  cases: { po_number: string; scenario_id: string | null; expected: Verdict; predicted: Verdict; correct: boolean }[];
}
export interface EvalImageResult {
  id: string; file: string; phrase: string; prompted_count: number;
  sam_count: number | null; true_count: number; correct: boolean | null; synthetic: true;
}
export interface EvalResults {
  schema_version: 1;
  generated_at: string;
  videos: { rows: VideoCountResult[]; count_summary: CountSummary; damage_summary: CountSummary };
  images: { synthetic: true; images_total: number; images_confirmed: number; rows: EvalImageResult[]; summary: CountSummary };
  verdicts: { served: VerdictScore | null; served_reason: string | null; agent: VerdictScore | null; agent_reason: string | null };
  latency: { model: string; role: string; calls: number; live_calls: number; p50_ms: number | null; p95_ms: number | null }[];
  cost: {
    rates_configured: boolean; currency: string | null; deliveries_processed: number;
    total_input_tokens: number; total_output_tokens: number;
    total_cost: number | null; cost_per_delivery: number | null;
    per_model: { model: string; input_tokens: number; output_tokens: number; cost: number | null }[];
  };
  not_measured: string[];
}
export interface VideoCountResult {
  scenario: string; category: string; noun_phrase: string | null;
  true_count: number; observed_count: number | null;
  true_damaged: number; flagged_damaged: number | null;
  source: "db" | "eval_counts" | "none";
  count_correct: boolean | null; damage_correct: boolean | null;
}

export const VERDICT_LABEL: Record<Verdict, string> = {
  approve: "Verified",
  partial_pay: "Partial pay",
  hold: "On hold",
  human_review: "Needs review",
};
