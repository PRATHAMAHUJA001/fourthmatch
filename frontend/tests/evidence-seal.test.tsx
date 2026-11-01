import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { EvidenceSeal } from "../src/components/evidence/EvidenceSeal";
import { server } from "../src/mocks/server";
import type { EvidencePackRead } from "../src/types/api";

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const pack: EvidencePackRead = {
  sha256: "ab12cd34ef56" + "0".repeat(52),
  created_at: "2026-11-01T10:00:00Z",
  verified: true,
  files: ["evidence_pack.json", "evidence_pack.pdf"],
};

function renderSeal() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><EvidenceSeal pack={pack} /></QueryClientProvider>);
}

describe("EvidenceSeal", () => {
  it("calls verify and shows 'Verified untouched' with the 12-char hash", async () => {
    let hit = "";
    server.use(http.get("/api/evidence/:hash/verify", ({ params }) => {
      hit = String(params.hash);
      return HttpResponse.json({ sha256: params.hash, verified: true, checked_at: "2026-11-01T10:05:00Z" });
    }));
    renderSeal();
    expect(await screen.findByText("Verified untouched")).toBeInTheDocument();
    expect(hit).toBe(pack.sha256);
    expect(screen.getByText("ab12cd34ef56")).toHaveTextContent(/^ab12cd34ef56$/);
  });

  it("shows a hash-mismatch failure state when verify says false", async () => {
    server.use(http.get("/api/evidence/:hash/verify", ({ params }) =>
      HttpResponse.json({ sha256: params.hash, verified: false, checked_at: "2026-11-01T10:05:00Z" })));
    renderSeal();
    expect(await screen.findByText(/Hash mismatch/)).toBeInTheDocument();
    expect(screen.queryByText("Verified untouched")).not.toBeInTheDocument();
  });

  it("shows 'Could not verify' when the request fails", async () => {
    server.use(http.get("/api/evidence/:hash/verify", () =>
      HttpResponse.json({ error: { code: "x", message: "boom" } }, { status: 500 })));
    renderSeal();
    expect(await screen.findByText("Could not verify")).toBeInTheDocument();
  });
});

describe("EvidenceSeal in the demo build", () => {
  it("never shows the dataset's hash as sealed and does not call verify", async () => {
    let called = false;
    server.use(http.get("/api/evidence/:hash/verify", () => { called = true; return HttpResponse.json({}); }));
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={qc}><EvidenceSeal pack={pack} demo /></QueryClientProvider>);
    expect(screen.getByTestId("demo-seal-note")).toHaveTextContent(/sealed .* on the live server/);
    expect(screen.queryByText("ab12cd34ef56")).toBeNull();
    expect(screen.queryByText("Verified untouched")).toBeNull();
    await new Promise((r) => setTimeout(r, 50));
    expect(called).toBe(false);
  });
});
