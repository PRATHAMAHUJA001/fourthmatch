/** Typed fetch wrappers over the FastAPI wire contract. Paise everywhere. */
import { useEffect, useRef, useState } from "react";
import type {
  AnalyticsRead, ApiErrorBody, CaseDetail, CaseSummary, DeliveryCreated, DockKpis, EvalRead,
  JobEventRead, PolicyRead, PurchaseOrderDetail, PurchaseOrderRead, RuleRead, SimulationRead,
} from "../types/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(path, init);
  if (!resp.ok) {
    let message = `Request failed (${resp.status})`;
    try {
      const body = (await resp.json()) as ApiErrorBody;
      if (body.error?.message) message = body.error.message;
    } catch {
      // non-JSON error body: keep the status-based message
    }
    throw new Error(message);
  }
  return (await resp.json()) as T;
}

const post = <T,>(path: string, body?: unknown) =>
  request<T>(path, {
    method: "POST",
    headers: body instanceof FormData ? undefined : { "Content-Type": "application/json" },
    body: body instanceof FormData ? body : body === undefined ? undefined : JSON.stringify(body),
  });

export const api = {
  cases: () => request<CaseSummary[]>("/api/cases"),
  case: (poId: number) => request<CaseDetail>(`/api/cases/${poId}`),
  purchaseOrders: () => request<PurchaseOrderRead[]>("/api/purchase-orders"),
  purchaseOrder: (id: number) => request<PurchaseOrderDetail>(`/api/purchase-orders/${id}`),
  dockKpis: () => request<DockKpis>("/api/dock/kpis"),
  policy: () => request<PolicyRead>("/api/policies/current"),
  rules: () => request<RuleRead[]>("/api/rules"),
  approveRule: (id: number) => post<RuleRead>(`/api/rules/${id}/approve`),
  rejectRule: (id: number) => post<RuleRead>(`/api/rules/${id}/reject`),
  simulate: (policyId: number, clause_id: string, text: string) =>
    post<SimulationRead>(`/api/policies/${policyId}/simulate`, { clause_id, text }),
  analytics: () => request<AnalyticsRead>("/api/analytics"),
  eval: () => request<EvalRead>("/api/eval"),
  verifyEvidence: (hash: string) => request<{ sha256: string; verified: boolean; checked_at: string }>(`/api/evidence/${hash}/verify`),
  createDelivery: (poId: number, video?: File | null) => {
    const form = new FormData();
    form.set("po_id", String(poId));
    if (video) form.set("video", video);
    return post<DeliveryCreated>("/api/deliveries", form);
  },
};

/* Back-compat names used by tests. */
export const getCases = api.cases;
export const getCase = api.case;

/**
 * Streams job events over SSE. Uses fetch + ReadableStream (works with MSW in
 * demo mode and with the FastAPI StreamingResponse in live mode).
 */
export function useJobEvents(deliveryId: number | null) {
  const [events, setEvents] = useState<JobEventRead[]>([]);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (deliveryId === null) return;
    setEvents([]);
    setDone(false);
    setError(null);
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    (async () => {
      try {
        const resp = await fetch(`/api/deliveries/${deliveryId}/events`, { signal: ctrl.signal });
        if (!resp.ok || !resp.body) throw new Error(`Event stream failed (${resp.status})`);
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buf = "";
        for (;;) {
          const { value, done: rdDone } = await reader.read();
          if (rdDone) break;
          buf += decoder.decode(value, { stream: true });
          let idx: number;
          while ((idx = buf.indexOf("\n\n")) >= 0) {
            const chunk = buf.slice(0, idx);
            buf = buf.slice(idx + 2);
            const data = chunk.split("\n").filter((l) => l.startsWith("data:")).map((l) => l.slice(5).trim()).join("");
            if (!data) continue;
            const ev = JSON.parse(data) as JobEventRead;
            setEvents((prev) => [...prev, ev]);
          }
        }
        setDone(true);
      } catch (e) {
        if (!ctrl.signal.aborted) setError(e instanceof Error ? e.message : "Stream failed");
      }
    })();
    return () => ctrl.abort();
  }, [deliveryId]);

  return { events, done, error };
}
