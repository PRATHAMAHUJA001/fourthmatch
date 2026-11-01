import { delay, http, HttpResponse } from "msw";
import type { SimulationRead } from "../types/api";
import {
  analytics, caseDetails, caseSummaries, dockKpis, evalResults, pipelineReplay, policy, purchaseOrders, rules,
} from "./dataset";

function err(code: string, message: string, status = 404) {
  return HttpResponse.json({ error: { code, message, request_id: "req_mock_01" } }, { status });
}

const LATENCY = 180;
let nextDelivery = 900;
const deliveryToPo = new Map<number, number>();
for (const c of caseDetails) if (c.delivery_id) deliveryToPo.set(c.delivery_id, c.po_id);

export const handlers = [
  http.get("/api/health", () => HttpResponse.json({ status: "ok" })),

  http.get("/api/purchase-orders", async () => {
    await delay(LATENCY);
    return HttpResponse.json(purchaseOrders.map(({ lines: _l, ...rest }) => rest));
  }),

  http.get("/api/purchase-orders/:id", async ({ params }) => {
    await delay(LATENCY);
    const po = purchaseOrders.find((p) => p.id === Number(params.id));
    if (!po) return err("po_not_found", `Purchase order ${params.id} was not found.`);
    return HttpResponse.json(po);
  }),

  http.get("/api/cases", async () => {
    await delay(LATENCY);
    return HttpResponse.json(caseSummaries);
  }),

  http.get("/api/cases/:id", async ({ params }) => {
    await delay(LATENCY);
    const found = caseDetails.find((c) => c.po_id === Number(params.id));
    if (!found) return err("po_not_found", `Purchase order ${params.id} was not found.`);
    return HttpResponse.json(found);
  }),

  http.get("/api/dock/kpis", async () => {
    await delay(LATENCY);
    return HttpResponse.json(dockKpis());
  }),

  http.post("/api/deliveries", async ({ request }) => {
    await delay(400);
    let poId = 2;
    try {
      const form = await request.formData();
      poId = Number(form.get("po_id") ?? 2);
    } catch { /* json or empty body */ }
    const id = ++nextDelivery;
    deliveryToPo.set(id, poId);
    return HttpResponse.json({ delivery_id: id, job_id: `job_mock_${id}`, po_id: poId }, { status: 201 });
  }),

  http.get("/api/deliveries/:id/events", ({ params }) => {
    const poId = deliveryToPo.get(Number(params.id)) ?? 2;
    const events = pipelineReplay(poId);
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      async start(controller) {
        let seq = 0;
        for (const e of events) {
          await delay(e.delay);
          seq += 1;
          const body = { id: seq, job_id: `job_mock_${params.id}`, seq, event_type: e.event_type, message: e.message, payload: e.payload, created_at: new Date().toISOString() };
          controller.enqueue(encoder.encode(`id: ${seq}\nevent: ${e.event_type}\ndata: ${JSON.stringify(body)}\n\n`));
        }
        controller.close();
      },
    });
    return new HttpResponse(stream, { headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" } });
  }),

  http.get("/api/policies/current", async () => {
    await delay(LATENCY);
    return HttpResponse.json(policy);
  }),

  http.get("/api/rules", async ({ request }) => {
    await delay(LATENCY);
    const status = new URL(request.url).searchParams.get("status");
    return HttpResponse.json(status ? rules.filter((r) => r.status === status) : rules);
  }),

  http.post("/api/rules/:id/approve", ({ params }) => {
    const rule = rules.find((r) => r.id === Number(params.id));
    if (!rule) return err("rule_not_found", `Rule ${params.id} was not found.`);
    rule.status = "approved";
    return HttpResponse.json(rule);
  }),

  http.post("/api/rules/:id/reject", ({ params }) => {
    const rule = rules.find((r) => r.id === Number(params.id));
    if (!rule) return err("rule_not_found", `Rule ${params.id} was not found.`);
    rule.status = "rejected";
    return HttpResponse.json(rule);
  }),

  http.post("/api/policies", async () => {
    await delay(900);
    return HttpResponse.json({ policy_version: "1.1-draft", rules, conflicts: [] }, { status: 201 });
  }),

  /** What-if: re-evaluates past cases against a draft tolerance for one clause.
   *  Mock evaluator: parses "N.N%" per category from clause 4.2 text and compares each
   *  stored line variance to it. The real endpoint compiles + evaluates in Python. */
  http.post("/api/policies/:id/simulate", async ({ request }) => {
    await delay(1400);
    const body = (await request.json().catch(() => ({}))) as { clause_id?: string; text?: string };
    const text = body.text ?? "";
    const pct = (cat: string) => {
      const label = cat.replace("_", " ");
      const m = text.match(new RegExp(`([0-9]+(?:\\.[0-9]+)?)%\\s+for\\s+${label}`, "i"));
      return m ? Number(m[1]) : null;
    };
    const changed: SimulationRead["changed"] = [];
    let before = 0;
    let after = 0;
    for (const c of caseDetails) {
      before += c.held_paise;
      let held = c.held_paise;
      let verdict = c.verdict;
      if (body.clause_id === "4.2" && (c.clauses ?? []).includes("4.2") && !(c.clauses ?? []).some((x) => x !== "4.2" && x !== "8.4")) {
        const line = c.lines.find((l) => (l.variance_pct ?? 0) < 0);
        const t = line ? pct(line.category) : null;
        if (line && t !== null && Math.abs(line.variance_pct ?? 0) <= t) {
          held = 0;
          verdict = c.lines.every((l) => l === line || l.verdict === "approve") ? "approve" : c.verdict;
        }
      }
      after += held;
      if (held !== c.held_paise || verdict !== c.verdict) {
        changed.push({ po_number: c.po_number, vendor_name: c.vendor_name, before: c.verdict, after: verdict, held_before_paise: c.held_paise, held_after_paise: held });
      }
    }
    const result: SimulationRead = {
      draft_policy_version: "1.1-draft", changed, unchanged_count: caseDetails.length - changed.length,
      held_before_paise: before, held_after_paise: after,
    };
    return HttpResponse.json(result);
  }),

  http.get("/api/analytics", async () => {
    await delay(LATENCY);
    return HttpResponse.json(analytics());
  }),

  http.get("/api/eval", async () => {
    await delay(LATENCY);
    return HttpResponse.json(evalResults());
  }),

  http.get("/api/evidence/:hash/verify", async ({ params }) => {
    await delay(700);
    return HttpResponse.json({ sha256: params.hash, verified: true, checked_at: new Date().toISOString() });
  }),
];
