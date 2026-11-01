import { http, HttpResponse } from "msw";
import { caseDetails, caseSummaries, purchaseOrderReads, purchaseOrders, rules } from "./data";

function err(code: string, message: string, status = 404) {
  return HttpResponse.json(
    { error: { code, message, request_id: "req_mock_01" } },
    { status },
  );
}

export const handlers = [
  http.get("/api/health", () => HttpResponse.json({ status: "ok" })),

  http.get("/api/purchase-orders", () => HttpResponse.json(purchaseOrderReads)),

  http.get("/api/purchase-orders/:id", ({ params }) => {
    const po = purchaseOrders.find((p) => p.id === Number(params.id));
    if (!po) return err("po_not_found", `Purchase order ${params.id} was not found.`);
    return HttpResponse.json(po);
  }),

  http.get("/api/cases", () => HttpResponse.json(caseSummaries)),

  http.get("/api/cases/:id", ({ params }) => {
    const found = caseDetails.find((c) => c.po_id === Number(params.id));
    if (!found) return err("po_not_found", `Purchase order ${params.id} was not found.`);
    return HttpResponse.json(found);
  }),

  http.post("/api/deliveries", async () =>
    HttpResponse.json({ delivery_id: 101, job_id: "job_mock_7f3a" }, { status: 201 }),
  ),

  http.get("/api/deliveries/:id/events", () => {
    const body =
      'id: 1\nevent: queued\ndata: {"seq":1,"event_type":"queued","message":"Job queued"}\n\n' +
      'id: 2\nevent: done\ndata: {"seq":2,"event_type":"done","message":"Pipeline complete"}\n\n';
    return new HttpResponse(body, { headers: { "Content-Type": "text/event-stream" } });
  }),

  http.get("/api/rules", ({ request }) => {
    const status = new URL(request.url).searchParams.get("status");
    return HttpResponse.json(status ? rules.filter((r) => r.status === status) : rules);
  }),

  http.post("/api/rules/:id/approve", ({ params }) => {
    const rule = rules.find((r) => r.id === Number(params.id));
    if (!rule) return err("rule_not_found", `Rule ${params.id} was not found.`);
    return HttpResponse.json({ ...rule, status: "approved" });
  }),

  http.post("/api/rules/:id/reject", ({ params }) => {
    const rule = rules.find((r) => r.id === Number(params.id));
    if (!rule) return err("rule_not_found", `Rule ${params.id} was not found.`);
    return HttpResponse.json({ ...rule, status: "rejected" });
  }),

  http.post("/api/policies", async () =>
    HttpResponse.json({ policy_version: "1.0", rules: [], conflicts: [] }, { status: 201 }),
  ),

  http.post("/api/policies/:id/simulate", async () =>
    HttpResponse.json({ policy_version: "1.0-draft", results: [], summary: { changed: 0, total: 0 } }),
  ),
];
