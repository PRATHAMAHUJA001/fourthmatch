import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RemarkPanel } from "../src/components/evidence/RemarkPanel";
import { caseDetails } from "../src/mocks/dataset";

describe("storekeeper remark (demo data)", () => {
  const withRemark = caseDetails.filter((c) => c.remark);

  it("is attached to exactly one case and its check is computed from that case's perception data", () => {
    expect(withRemark).toHaveLength(1);
    const c = withRemark[0];
    const damaged = c.lines.reduce((s, l) => s + (l.perception?.damaged_track_ids.length ?? 0), 0);
    const claim = c.remark!.check!.items[0];
    expect(claim.observed).toBe(damaged);
    expect(c.remark!.check!.status).toBe(damaged >= (claim.claim.quantity ?? 0) ? "supported" : "not_supported");
  });

  it("labels the transcript as context and shows the chip with text when not supported", () => {
    render(<RemarkPanel remark={{ transcript: "Two boxes are damaged.", check: { status: "not_supported", items: [{ claim: { kind: "damage", category: "cartons", quantity: 2, text: "Two boxes are damaged" }, verdict: "not_supported", observed: 0 }] } }} />);
    expect(screen.getByText("Storekeeper remark — context, not evidence")).toBeInTheDocument();
    expect(screen.getAllByText(/Remark not supported by video/).length).toBeGreaterThan(0);
    expect(screen.getByTestId("remark-not-supported")).toHaveTextContent("Remark not supported by video");
  });

  it("shows no chip when the remark is supported", () => {
    render(<RemarkPanel remark={{ transcript: "ok", check: { status: "supported", items: [] } }} />);
    expect(screen.queryByTestId("remark-not-supported")).toBeNull();
  });
});
