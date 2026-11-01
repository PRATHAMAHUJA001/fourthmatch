import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
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

describe("Cases (MSW)", () => {
  it("lists cases with verdict badge and Indian-formatted at-risk", async () => {
    renderAt("/cases");
    expect(await screen.findByText("FM/PO/26-27/002")).toBeInTheDocument();
    expect(screen.getAllByText("Partial pay").length).toBeGreaterThan(0);
    expect(screen.getAllByText("₹1,650").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Acme Packaging Ltd").length).toBeGreaterThan(0);
  });

  it("detail shows the four-way quantity comparison and cited clause", async () => {
    renderAt("/cases/2");
    expect(await screen.findByText("CTN-550")).toBeInTheDocument();
    expect(screen.getByText("§4.2")).toBeInTheDocument();
    expect(screen.getByText("R-4.2-cartons")).toBeInTheDocument();
    expect(screen.getByText(/Quantity variance beyond tolerance/)).toBeInTheDocument();
    expect(screen.getByText("SAM tracks")).toBeInTheDocument();
    expect(screen.getAllByText("Partial pay").length).toBeGreaterThan(0);
  });

  it("weak video evidence is needs-review, never verified", async () => {
    renderAt("/cases/5");
    expect(await screen.findByText("STL-HR-2T")).toBeInTheDocument();
    expect(screen.getAllByText("Needs review").length).toBeGreaterThan(0);
    expect(screen.getByText("Evidence insufficient")).toBeInTheDocument();
  });
});
