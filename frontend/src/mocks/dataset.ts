/**
 * Mock dataset for frontend-only demo mode.
 *
 * Nothing here hardcodes a count, quantity or verdict. Every number is read from
 * the repo's own data files at build time:
 *   - data/ground_truth.json      (documents, expected verdicts, Python-computed amounts)
 *   - data/eval_counts.json       (real SAM pipeline output per scenario line)
 *   - data/policy/receiving_policy.md (verbatim clauses)
 *   - samples/scenarios/manifest.json (via ground_truth)
 * Dates, latencies and the 30-day trend are synthetic presentation data.
 */
import groundTruthRaw from "../../../data/ground_truth.json";
import evalCountsRaw from "../../../data/eval_counts.json";
import policyMd from "../../../data/policy/receiving_policy.md?raw";
import type {
  AgentStep, AnalyticsRead, CaseDetail, CaseLineRead, CaseSummary, CitedRule, DockKpis,
  EvalRead, PolicyClause, PolicyRead, PurchaseOrderDetail, RuleRead, Verdict,
} from "../types/api";

interface GtCase {
  po_number: string;
  scenario_id: string | null;
  source: "video" | "documents_only";
  video_path: string | null;
  vendor: string;
  documents: {
    po: { qty: number; unit: string; category: string }[];
    grn: { qty: number; damaged: number }[];
    invoice: { number: string; lines: { qty: number; unit_price_inr: number }[]; total_paise: number };
  };
  truth: { qty: number; damaged: number; unit: string }[] | null;
  discrepancy_types: string[];
  correct_verdict: Verdict;
  policy_clauses: string[];
  variance: { qty: number; pct: number }[];
  amount_at_risk_paise: number;
  requires_debit_note: boolean;
  debit_qty: number;
}
interface GroundTruth {
  policy_version: string;
  policy_numbers: { quantity_tolerance_pct: Record<string, number>; price_tolerance_pct: number; min_track_confidence: number };
  scenarios_and_discrepancies: GtCase[];
}
interface EvalCount {
  scenario: string; category: string; noun_phrase: string; observed_count: number; max_visible: number;
  true_count: number; evidence_quality: "reliable" | "insufficient"; reasons: string[];
  true_damaged: number; flagged_damaged: number; damaged_track_ids: string[];
  footage_needed: string | null; result: "PASS" | "FAIL";
}

const gt = groundTruthRaw as unknown as GroundTruth;
const evalCounts = evalCountsRaw as unknown as EvalCount[];

/* ——— policy ——— */
function parsePolicy(md: string): PolicyRead {
  const clauses: PolicyClause[] = [];
  let section = "";
  for (const line of md.split("\n")) {
    const h = line.match(/^##\s+\d+\s+(.*)$/);
    if (h) { section = h[1].trim(); continue; }
    const c = line.match(/^\*\*(\d+\.\d+)\*\*\s+(.*)$/);
    if (c) clauses.push({ clause_id: c[1], section, text: c[2].trim() });
  }
  const docNo = md.match(/Document No\.\s*([A-Z0-9-]+)/)?.[1] ?? "";
  const eff = md.match(/Effective Date:\s*([0-9-]+)/)?.[1] ?? "";
  return {
    id: 1, version: gt.policy_version, title: "Receiving and Payment-Hold Policy",
    document_no: docNo, effective_date: eff, clauses,
  };
}
export const policy = parsePolicy(policyMd);
const clauseText = (id: string) => policy.clauses.find((c) => c.clause_id === id)?.text ?? "";

/* ——— rules (compiled view of the policy; tolerances read from ground_truth policy_numbers) ——— */
const tol = gt.policy_numbers.quantity_tolerance_pct;
const CLAUSE_ACTION: Record<string, Verdict> = { "4.2": "partial_pay", "5.1": "hold", "5.2": "partial_pay", "5.3": "hold", "6.1": "partial_pay", "8.3": "human_review", "8.4": "partial_pay" };

export const rules: RuleRead[] = [
  ...Object.entries(tol).map(([cat, pct], i) => ({
    id: i + 1, rule_id: `R-4.2-${cat}`, goods_category: cat, action: "partial_pay", signoff_role: "stores_manager",
    source_clause: "4.2", source_text: clauseText("4.2"), ambiguity: null, status: "approved", tolerance_pct: pct,
    condition: { field: "variance_pct", op: ">", value: pct },
  })),
  { id: 10, rule_id: "R-5.1-price", goods_category: null, action: "hold", signoff_role: "purchase_manager", source_clause: "5.1", source_text: clauseText("5.1"), ambiguity: null, status: "approved", tolerance_pct: gt.policy_numbers.price_tolerance_pct, condition: { field: "price_variance_pct", op: ">", value: gt.policy_numbers.price_tolerance_pct } },
  { id: 11, rule_id: "R-5.2-overbill", goods_category: null, action: "partial_pay", signoff_role: null, source_clause: "5.2", source_text: clauseText("5.2"), ambiguity: null, status: "approved", tolerance_pct: 0, condition: { field: "invoiced_vs_po_pct", op: ">", value: 0 } },
  { id: 12, rule_id: "R-5.3-duplicate", goods_category: null, action: "hold", signoff_role: null, source_clause: "5.3", source_text: clauseText("5.3"), ambiguity: null, status: "approved", tolerance_pct: null, condition: { field: "duplicate_invoice", op: "==", value: true } },
  { id: 13, rule_id: "R-6.1-damage", goods_category: null, action: "partial_pay", signoff_role: null, source_clause: "6.1", source_text: clauseText("6.1"), ambiguity: null, status: "approved", tolerance_pct: 0, condition: { field: "damage_count", op: ">", value: 0 } },
  { id: 14, rule_id: "R-8.2-confidence", goods_category: null, action: "hold", signoff_role: null, source_clause: "8.2", source_text: clauseText("8.2"), ambiguity: "Confidence is a per-track SAM score, not a field in the rule catalog; enforced in Python by evidence_quality instead.", status: "pending_approval", tolerance_pct: null, condition: null },
  { id: 15, rule_id: "R-8.4-video-prevails", goods_category: null, action: "partial_pay", signoff_role: null, source_clause: "8.4", source_text: clauseText("8.4"), ambiguity: null, status: "approved", tolerance_pct: null, condition: { field: "observed_count", op: "<", value: "grn_qty" } },
  { id: 16, rule_id: "R-7.4-release-undisputed", goods_category: null, action: "partial_pay", signoff_role: "finance_controller", source_clause: "7.4", source_text: clauseText("7.4"), ambiguity: null, status: "pending_approval", tolerance_pct: null, condition: null },
];
const ruleFor = (clause: string, category?: string): CitedRule => {
  const r = rules.find((x) => x.source_clause === clause && (category ? x.goods_category === category || x.goods_category === null : true))
    ?? rules.find((x) => x.source_clause === clause);
  return { rule_id: r?.rule_id ?? `R-${clause}`, source_clause: clause, source_text: clauseText(clause), action: CLAUSE_ACTION[clause] ?? "hold" };
};

/* ——— cases ——— */
const SKU: Record<string, { sku: string; desc: string }> = {
  cartons: { sku: "CTN-550", desc: "Corrugated cartons, 5-ply" },
  bagged_material: { sku: "BAG-25K", desc: "Bagged material, 25 kg sacks" },
  steel_coils: { sku: "STL-HR-2T", desc: "HR steel coils, 2 t" },
};
const vendorIds = new Map<string, number>();
const vendorId = (name: string) => {
  if (!vendorIds.has(name)) vendorIds.set(name, vendorIds.size + 1);
  return vendorIds.get(name)!;
};
const evalFor = (scenario: string | null, category: string) =>
  scenario ? evalCounts.find((e) => e.scenario === scenario && e.category.replace(" ", "_") === category) ?? null : null;

const day = (offset: number) => {
  const d = new Date(Date.UTC(2026, 9, 18 + offset));
  return d.toISOString().slice(0, 10);
};
const decidedAt = (idx: number) => new Date(Date.UTC(2026, 9, 31, 4, 12 + idx * 37, (idx * 17) % 60)).toISOString();

const sha = (seed: string) => {
  let h1 = 0x811c9dc5;
  let out = "";
  for (let round = 0; round < 8; round++) {
    for (let i = 0; i < seed.length; i++) h1 = Math.imul(h1 ^ seed.charCodeAt(i) ^ round, 0x01000193) >>> 0;
    out += h1.toString(16).padStart(8, "0");
  }
  return out;
};

function buildCase(c: GtCase, idx: number): CaseDetail {
  const poId = Number(c.po_number.split("/").pop());
  const isVideo = c.source === "video";
  const isPriceCase = c.discrepancy_types.includes("invoice_price_above_po");
  const isDuplicate = c.discrepancy_types.includes("duplicate_invoice_number");
  const lines: CaseLineRead[] = c.documents.po.map((po, i) => {
    const grn = c.documents.grn[i];
    const inv = c.documents.invoice.lines[i];
    const ev = evalFor(c.scenario_id, po.category);
    const invPrice = Math.round(inv.unit_price_inr * 100);
    // Price cases: PO price recovered from the Python-computed amount at risk.
    const poPrice = isPriceCase ? invPrice - Math.round(c.amount_at_risk_paise / inv.qty) : invPrice;
    const observed = isVideo ? ev?.observed_count ?? null : grn.qty - grn.damaged;
    const damage = isVideo ? ev?.flagged_damaged ?? 0 : grn.damaged;
    const variance = c.variance[i];
    const short = variance && variance.qty > 0;
    const clauses = c.policy_clauses.filter(() => {
      if (c.documents.po.length === 1) return true;
      return short; // multi-line: clauses apply to the short line only
    });
    const lineVerdict: Verdict = clauses.length === 0 ? "approve" : c.correct_verdict;
    const lineValue = inv.qty * invPrice;
    const atRisk = c.documents.po.length === 1 ? c.amount_at_risk_paise : short ? c.amount_at_risk_paise : 0;
    return {
      po_line_id: poId * 10 + i + 1, line_no: i + 1, sku: SKU[po.category].sku, description: SKU[po.category].desc,
      category: po.category, unit: po.unit, po_qty: po.qty, grn_qty: grn.qty, invoiced_qty: inv.qty,
      observed_count: observed, damage_count: damage,
      evidence_source: isVideo ? "video" : "document",
      evidence_quality: isVideo ? ev?.evidence_quality ?? "insufficient" : null,
      unit_price_paise: invPrice, po_unit_price_paise: poPrice, line_value_paise: lineValue,
      variance_pct: variance ? -variance.pct : null,
      verdict: lineVerdict, held_paise: lineVerdict === "approve" ? 0 : atRisk, at_risk_paise: atRisk,
      signoff_roles: lineVerdict === "approve" ? [] : ["stores_manager"],
      cited_rules: clauses.map((cl) => ruleFor(cl, po.category)),
      perception: isVideo && ev ? {
        noun_phrase: ev.noun_phrase, observed_count: ev.observed_count, max_visible: ev.max_visible,
        track_ids: Array.from({ length: ev.observed_count }, (_, t) => String(t)),
        damaged_track_ids: ev.damaged_track_ids, reasons: ev.reasons, footage_needed: ev.footage_needed,
      } : null,
    };
  });
  const held = lines.reduce((s, l) => s + l.held_paise, 0) || (c.correct_verdict === "approve" ? 0 : c.amount_at_risk_paise);
  const verdict = c.correct_verdict;
  const triggered = [...new Set(lines.flatMap((l) => l.cited_rules.map((r) => r.rule_id)))];
  const base: CaseDetail = {
    po_id: poId, po_number: c.po_number, vendor_id: vendorId(c.vendor), vendor_name: c.vendor,
    scenario_id: c.scenario_id, status: "received",
    order_date: day(idx), expected_date: day(idx + 5),
    total_paise: lines.reduce((s, l) => s + l.po_qty * l.po_unit_price_paise, 0),
    verdict, held_paise: verdict === "approve" ? 0 : held, at_risk_paise: c.amount_at_risk_paise,
    policy_version: gt.policy_version, lines_evaluated: lines.length, lines_total: lines.length,
    discrepancy_types: c.discrepancy_types, clauses: c.policy_clauses,
    evidence_source: isVideo ? "video" : "document", decided_at: decidedAt(idx),
    delivery_id: isVideo ? 100 + poId : null,
    grn_number: `GRN/26-27/${String(poId).padStart(4, "0")}`,
    invoice_number: c.documents.invoice.number,
    invoice_total_paise: c.documents.invoice.total_paise,
    triggered_rule_ids: triggered, signoff_roles: verdict === "approve" ? [] : ["stores_manager", "finance_controller"],
    lines,
    video_url: c.video_path ? `/demo/${c.video_path.split("/").pop()}` : null,
    evidence_pack: verdict === "approve" ? null : {
      sha256: sha(c.po_number + c.documents.invoice.number), created_at: decidedAt(idx), verified: true,
      files: ["evidence_pack.pdf", "evidence_pack.json", ...(c.requires_debit_note || verdict === "partial_pay" ? ["debit_note.pdf"] : [])],
    },
  };
  base.decision = buildDecision(base, c, isDuplicate);
  return base;
}

const DISCREPANCY_LABEL: Record<string, string> = {
  grn_contradicted_by_video: "GRN contradicted by video",
  short_shipment_beyond_tolerance: "Short shipment",
  damaged_units_invoiced: "Damaged units invoiced",
  invoice_price_above_po: "Price above PO",
  invoice_qty_exceeds_po: "Invoice qty above PO",
  duplicate_invoice_number: "Duplicate invoice",
};
export const discrepancyLabel = (t: string) => DISCREPANCY_LABEL[t] ?? t.replaceAll("_", " ");

const plural = (u: string, n: number) => (n === 1 ? u : u.endsWith("x") ? `${u}es` : `${u}s`);

function inr(paise: number) {
  return "₹" + new Intl.NumberFormat("en-IN").format(Math.round(paise / 100));
}

function buildDecision(cd: CaseDetail, c: GtCase, duplicate: boolean) {
  const trace: AgentStep[] = [];
  let seq = 0;
  // Latency is unknown until the agent runs live (model_calls table); never invented here.
  const push = (tool: string, args: Record<string, unknown>, result: Record<string, unknown>, _base = 0) =>
    trace.push({ seq: ++seq, tool, args, result, latency_ms: _base < 0 ? _base : null });

  push("get_case", { delivery_id: cd.delivery_id ?? cd.po_id }, {
    po: cd.po_number, vendor: cd.vendor_name, lines: cd.lines.length,
    grn: cd.grn_number, invoice: cd.invoice_number, perception: cd.evidence_source === "video" ? "attached" : "none (documents only)",
  }, 18);
  for (const l of cd.lines) {
    push("compute_variance", { po_line_id: l.po_line_id }, {
      po: l.po_qty, grn: l.grn_qty, invoiced: l.invoiced_qty, observed: l.observed_count,
      variance_pct: l.variance_pct, value_at_risk_paise: l.at_risk_paise,
    }, 4);
  }
  const cats = [...new Set(cd.lines.map((l) => l.category))];
  for (const cat of cats) {
    const applicable = rules.filter((r) => r.status === "approved" && (r.goods_category === cat || r.goods_category === null));
    push("get_rules", { goods_category: cat }, { rules: applicable.map((r) => r.rule_id) }, 5);
  }
  for (const l of cd.lines) {
    const fired = new Set(l.cited_rules.map((r) => r.rule_id));
    const check = [rules.find((r) => r.goods_category === l.category)!, ...rules.filter((r) => r.goods_category === null && r.status === "approved")];
    for (const r of check) {
      push("evaluate_rule", { rule_id: r.rule_id, po_line_id: l.po_line_id }, {
        fired: fired.has(r.rule_id ?? ""),
        why: fired.has(r.rule_id ?? "") ? `clause ${r.source_clause}: ${r.condition?.field} ${r.condition?.op} ${r.condition?.value}` : "condition not met",
      }, 3);
    }
  }
  if (cd.verdict === "partial_pay") {
    push("draft_debit_note", { invoice_id: cd.invoice_number, lines: cd.lines.filter((l) => l.held_paise > 0).map((l) => l.po_line_id) },
      { debit_note: `DN/26-27/${String(cd.po_id).padStart(4, "0")}`, amount_paise: cd.held_paise }, 22);
  }
  const short = cd.lines.find((l) => (l.variance_pct ?? 0) < 0);
  const summary = (() => {
    if (cd.verdict === "approve") return `PO, GRN, invoice and dock video agree on every line. Invoice ${cd.invoice_number} can be paid in full on standard terms.`;
    if (c.discrepancy_types.includes("grn_contradicted_by_video") && short)
      return `Dock video shows ${short.observed_count} ${plural(short.unit, short.observed_count ?? 0)} against ${short.invoiced_qty} on the GRN and invoice, so the signed GRN is contradicted under clause 8.4. Release the matched portion and hold ${inr(cd.held_paise)} for the shortfall under clause 4.2.`;
    if (c.discrepancy_types.includes("damaged_units_invoiced"))
      return `${cd.lines[0].damage_count} damaged ${cd.lines[0].unit} was invoiced at full price; clause 6.1 sets its payable quantity to zero. Pay the rest and raise a debit note for ${inr(cd.held_paise)}.`;
    if (duplicate) return `Invoice ${cd.invoice_number} repeats a supplier invoice number already booked. Under clause 5.3 the full ${inr(cd.held_paise)} is held until the supplier proves it is not a second presentation.`;
    if (c.discrepancy_types.includes("invoice_price_above_po")) return `Invoice unit price is above the PO price beyond the ${gt.policy_numbers.price_tolerance_pct}% tolerance in clause 5.1. ${inr(cd.held_paise)} is held pending Purchase clarification.`;
    if (c.discrepancy_types.includes("invoice_qty_exceeds_po")) return `Invoiced quantity exceeds the PO with 0% tolerance under clause 5.2. The excess value of ${inr(cd.held_paise)} is held until the PO is amended.`;
    return `Received quantity is short of the PO beyond the category tolerance in clause 4.2. ${inr(cd.held_paise)} is withheld pending Stores Manager review.`;
  })();
  const action = cd.verdict === "approve" ? "Release payment on standard 30-day terms."
    : cd.verdict === "hold" ? "Notify Purchase and supplier within 3 working days (clause 7.2)."
      : "Issue debit note within 7 working days and release the undisputed portion (clauses 6.3, 7.4).";
  push("record_decision", { verdict: cd.verdict, amount_held_paise: cd.held_paise }, { recorded: true, amount_check: "matches Python recompute" }, 9);
  return {
    verdict: cd.verdict!, amount_held_paise: cd.held_paise, summary_en: summary, recommended_action: action,
    model: "muse-spark-1.3", trace,
  };
}

export const caseDetails: CaseDetail[] = gt.scenarios_and_discrepancies.map(buildCase);
export const caseSummaries: CaseSummary[] = caseDetails.map(
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  ({ lines: _l, decision: _d, evidence_pack: _e, delivery_id: _di, grn_number: _g, invoice_number: _i, triggered_rule_ids: _t, signoff_roles: _s, video_url: _v, invoice_total_paise: _it, ...rest }) => rest,
);

export const purchaseOrders: PurchaseOrderDetail[] = caseDetails.map((c) => ({
  id: c.po_id, po_number: c.po_number, vendor_id: c.vendor_id, vendor_name: c.vendor_name,
  order_date: c.order_date, expected_date: c.expected_date, status: "open", currency: "INR",
  total_paise: c.total_paise, scenario_id: c.scenario_id, synthetic: true,
  lines: c.lines.map((l) => ({
    id: l.po_line_id, line_no: l.line_no, category: l.category, sku: l.sku, description: l.description,
    unit: l.unit, qty_ordered: l.po_qty, unit_price_paise: l.po_unit_price_paise,
    tolerance_pct: tol[l.category] ?? 0, line_total_paise: l.po_qty * l.po_unit_price_paise,
  })),
}));

/* ——— Dock Live ——— */
export function dockKpis(): DockKpis {
  const decided = caseSummaries.filter((c) => c.verdict);
  return {
    held_today_paise: decided.reduce((s, c) => s + c.held_paise, 0),
    deliveries_verified: decided.filter((c) => c.verdict === "approve").length,
    deliveries_total: decided.length,
    discrepancy_rate_pct: Math.round((decided.filter((c) => c.verdict !== "approve").length / decided.length) * 1000) / 10,
    avg_time_to_verdict_s: null, // filled from job timings when the backend runs live
  };
}

/* ——— Analytics ——— */
export function analytics(): AnalyticsRead {
  const byVendor = new Map<string, { held: number; cases: number; disc: number }>();
  for (const c of caseSummaries) {
    const v = byVendor.get(c.vendor_name) ?? { held: 0, cases: 0, disc: 0 };
    v.held += c.held_paise; v.cases += 1; v.disc += c.verdict !== "approve" ? 1 : 0;
    byVendor.set(c.vendor_name, v);
  }
  const mix = new Map<string, number>();
  for (const c of caseSummaries) for (const t of c.discrepancy_types ?? []) mix.set(t, (mix.get(t) ?? 0) + 1);
  // Synthetic 30-day history (deterministic), clearly labelled synthetic in the UI.
  let s = 42;
  const rnd = () => ((s = (s * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff);
  const trend = Array.from({ length: 30 }, (_, i) => {
    const d = new Date(Date.UTC(2026, 9, 2 + i));
    const deliveries = 6 + Math.floor(rnd() * 9);
    const discrepancies = Math.min(deliveries, Math.floor(rnd() * (i > 20 ? 4 : 3)) + (i % 7 === 3 ? 2 : 0));
    return { date: d.toISOString().slice(0, 10), deliveries, discrepancies };
  });
  const vendor_risk = [...byVendor.entries()].map(([vendor_name, v]) => ({
    vendor_name, cases: v.cases, discrepancies: v.disc, held_paise: v.held,
    risk_score: Math.round((v.disc / v.cases) * 100),
  })).sort((a, b) => b.risk_score - a.risk_score || b.held_paise - a.held_paise);
  return {
    held_by_vendor: [...byVendor.entries()].map(([vendor_name, v]) => ({ vendor_name, held_paise: v.held, cases: v.cases }))
      .sort((a, b) => b.held_paise - a.held_paise),
    trend,
    type_mix: [...mix.entries()].map(([type, count]) => ({ type, count })).sort((a, b) => b.count - a.count),
    vendor_risk,
  };
}

/* ——— Eval ——— */
export function evalResults(): EvalRead {
  const labels: Verdict[] = ["approve", "partial_pay", "hold", "human_review"];
  // Predicted verdict = what the case served; truth = ground_truth correct_verdict.
  const pairs = gt.scenarios_and_discrepancies.map((c, i) => [c.correct_verdict, caseDetails[i].verdict ?? "human_review"] as const);
  const idx = (v: Verdict) => labels.indexOf(v);
  const matrix = labels.map(() => labels.map(() => 0));
  for (const [t, p] of pairs) matrix[idx(t)][idx(p)] += 1;
  const verdict_metrics = labels.map((label, i) => {
    const tp = matrix[i][i];
    const predicted = matrix.reduce((s, row) => s + row[i], 0);
    const support = matrix[i].reduce((s, x) => s + x, 0);
    const precision = predicted ? tp / predicted : null;
    const recall = support ? tp / support : null;
    const f1 = precision !== null && recall !== null && precision + recall > 0 ? (2 * precision * recall) / (precision + recall) : null;
    return { label, precision, recall, f1, support };
  });
  const counts = evalCounts.map((e) => ({
    scenario: e.scenario, category: e.category, noun_phrase: e.noun_phrase, true_count: e.true_count,
    observed_count: e.observed_count, max_visible: e.max_visible, evidence_quality: e.evidence_quality,
    true_damaged: e.true_damaged, flagged_damaged: e.flagged_damaged, result: e.result,
  }));
  return {
    verdict_metrics,
    confusion: { labels, matrix },
    counts,
    latency: [
      { model: "muse-spark-1.3", role: "Perception · scene + noun phrases", calls: 4, p50_ms: null, p95_ms: null },
      { model: "sam-3.1", role: "Segmentation · tracks", calls: 10, p50_ms: null, p95_ms: null },
      { model: "muse-spark-1.3", role: "Damage check · crops", calls: 44, p50_ms: null, p95_ms: null },
      { model: "muse-spark-1.3", role: "Decision agent · reasoning high", calls: 12, p50_ms: null, p95_ms: null },
      { model: "muse-spark-1.3", role: "Policy compiler", calls: 41, p50_ms: null, p95_ms: null },
    ],
    cases_total: pairs.length,
    verdict_accuracy: pairs.filter(([t, p]) => t === p).length / pairs.length,
    count_accuracy: counts.filter((c) => c.result === "PASS").length / counts.length,
  };
}

/* ——— pipeline replay (SSE) ——— */
export interface ReplayEvent { event_type: string; message: string; payload: Record<string, unknown>; delay: number }

export function pipelineReplay(poId: number): ReplayEvent[] {
  const c = caseDetails.find((x) => x.po_id === poId) ?? caseDetails[1];
  const videoLines = c.lines.filter((l) => l.perception);
  const ev: ReplayEvent[] = [
    { event_type: "queued", message: "Job queued", payload: {}, delay: 250 },
    { event_type: "uploading", message: "Hashing video (SHA-256) and uploading to Files API", payload: {}, delay: 500 },
    { event_type: "uploading_finished", message: "Upload cached by video hash", payload: { cache: "hit" }, delay: 900 },
    { event_type: "understanding", message: "muse-spark-1.3 watching the dock video", payload: { model: "muse-spark-1.3" }, delay: 400 },
    {
      event_type: "understanding_finished", message: "Noun phrases chosen for each PO line",
      payload: { phrases: videoLines.map((l) => l.perception!.noun_phrase), camera_motion: "pan", occlusion: "partial" }, delay: 1800,
    },
    { event_type: "tracking", message: "sam-3.1 segmenting and tracking objects", payload: { model: "sam-3.1" }, delay: 400 },
  ];
  for (const l of videoLines) {
    const n = l.perception!.observed_count;
    for (let k = 1; k <= n; k++) {
      ev.push({ event_type: "tracking_progress", message: `Track ${k - 1} confirmed`, payload: { phrase: l.perception!.noun_phrase, po_line_id: l.po_line_id, tracks: k, track_id: String(k - 1) }, delay: 260 + ((k * 97) % 180) });
    }
  }
  ev.push(
    { event_type: "tracking_finished", message: "Tracks merged and counted in Python", payload: { counts: videoLines.map((l) => ({ po_line_id: l.po_line_id, observed: l.observed_count })) }, delay: 500 },
    { event_type: "damage_check", message: "Inspecting crops of every track", payload: {}, delay: 400 },
    { event_type: "damage_check_finished", message: "Damage check complete", payload: { damaged: videoLines.flatMap((l) => l.perception!.damaged_track_ids) }, delay: 1500 },
    { event_type: "reconciling", message: "Four-way match: PO · GRN · Invoice · Vision", payload: {}, delay: 900 },
    { event_type: "applying_policy", message: "Decision agent evaluating approved rules", payload: { model: "muse-spark-1.3", rules: c.triggered_rule_ids }, delay: 1400 },
    { event_type: "verdict", message: `Verdict: ${c.verdict}`, payload: { verdict: c.verdict, held_paise: c.held_paise }, delay: 900 },
    { event_type: "done", message: "done", payload: { po_id: c.po_id }, delay: 300 },
  );
  return ev;
}
