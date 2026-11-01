import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { formatINR } from "../src/lib/format";
import { caseDetails } from "../src/mocks/dataset";
import { server } from "../src/mocks/server";
import { CaseDetail } from "../src/pages/CaseDetail";
import { Cases } from "../src/pages/Cases";

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function renderAt(path: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="cases" element={<Cases />} />
          <Route path="cases/:poId" element={<CaseDetail />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// Expected values come from the dataset (itself built from data/ground_truth.json + eval_counts.json).
const short = caseDetails.find((c) => c.scenario_id === "scn2_short")!;
const docsOnly = caseDetails.find((c) => c.evidence_source === "document" && c.verdict === "hold")!;

describe("Cases (MSW)", () => {
  it("lists every case with its verdict badge and Indian-formatted held amount", async () => {
    renderAt("/cases");
    expect(await screen.findByText(short.po_number)).toBeInTheDocument();
    expect(screen.getAllByText("Partial pay").length).toBeGreaterThan(0);
    expect(screen.getAllByText(formatINR(short.held_paise)).length).toBeGreaterThan(0);
    expect(screen.getAllByText(short.vendor_name).length).toBeGreaterThan(0);
  });

  it("case detail shows the four-way match, the vision count and the verbatim clause", async () => {
    renderAt(`/cases/${short.po_id}`);
    const strip = await screen.findByRole("heading", { name: /the fourth match/i });
    const panel = strip.closest("section")!;
    const line = short.lines[0];
    expect(within(panel).getByText(line.sku)).toBeInTheDocument();
    expect(within(panel).getAllByText(String(line.observed_count)).length).toBeGreaterThan(0);
    expect(within(panel).getAllByText(String(line.po_qty)).length).toBeGreaterThanOrEqual(3);
    expect(screen.getAllByText("§4.2").length).toBeGreaterThan(0);
    expect(screen.getByText(/quantity tolerance for acceptance without escalation/i)).toBeInTheDocument();
    expect(within(panel).getByText("contradicted · §8.4")).toBeInTheDocument();
  });

  it("documents-only case says there is no dock video and shows the hold", async () => {
    renderAt(`/cases/${docsOnly.po_id}`);
    expect(await screen.findByText("Documents only")).toBeInTheDocument();
    expect(screen.getAllByText("On hold").length).toBeGreaterThan(0);
    expect(screen.getByText("no dock video")).toBeInTheDocument();
  });
});
