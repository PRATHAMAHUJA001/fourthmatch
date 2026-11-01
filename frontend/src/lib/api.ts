/** Typed fetch wrappers over the FastAPI wire contract. Paise everywhere. */
import type { ApiErrorBody, CaseDetail, CaseSummary } from "../types/api";

async function getJson<T>(path: string): Promise<T> {
  const resp = await fetch(path);
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

export function getCases(): Promise<CaseSummary[]> {
  return getJson<CaseSummary[]>("/api/cases");
}

export function getCase(poId: number): Promise<CaseDetail> {
  return getJson<CaseDetail>(`/api/cases/${poId}`);
}
