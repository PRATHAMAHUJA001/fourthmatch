import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { mismatches, FourMatchStrip } from "../src/components/ui/FourMatch";
import { Money } from "../src/components/ui/Money";
import { StatusBadge } from "../src/components/ui/StatusBadge";

describe("StatusBadge: never colour alone", () => {
  it("renders a label and a glyph for every verdict", () => {
    const cases = [["approve", "Verified"], ["partial_pay", "Partial pay"], ["hold", "On hold"], ["human_review", "Needs review"]] as const;
    for (const [verdict, label] of cases) {
      const { container, unmount } = render(<StatusBadge verdict={verdict} />);
      expect(screen.getByText(label)).toBeInTheDocument();
      expect(container.querySelector("svg")).not.toBeNull();
      unmount();
    }
  });
  it("renders fraud risk and weak evidence distinctly", () => {
    render(<><StatusBadge fraud /><StatusBadge quality="insufficient" /></>);
    expect(screen.getByText("Fraud risk")).toBeInTheDocument();
    expect(screen.getByText("Evidence insufficient")).toBeInTheDocument();
  });
  it("shows Not decided when there is no verdict", () => {
    render(<StatusBadge verdict={null} />);
    expect(screen.getByText("Not decided")).toBeInTheDocument();
  });
});

describe("Money", () => {
  it("renders Indian grouping", () => {
    render(<Money paise={124500000} />);
    expect(screen.getByText("₹12,45,000")).toBeInTheDocument();
  });
});

describe("Four-match", () => {
  it("flags only the sources that disagree with the PO", () => {
    expect(mismatches({ po: 14, grn: 14, invoice: 14, vision: 12 })).toEqual({ po: false, grn: false, invoice: false, vision: true });
    expect(mismatches({ po: 12, grn: 12, invoice: 12, vision: 12 })).toEqual({ po: false, grn: false, invoice: false, vision: false });
    expect(mismatches({ po: 10, grn: null, invoice: 11, vision: null })).toEqual({ po: false, grn: false, invoice: true, vision: false });
  });
  it("draws ≠ before a mismatching cell and = otherwise", () => {
    render(<FourMatchStrip values={{ po: 14, grn: 14, invoice: 14, vision: 12 }} variancePct={-14.29} />);
    expect(screen.getAllByText("=").length).toBe(2);
    expect(screen.getByText("≠")).toBeInTheDocument();
    expect(screen.getByText("−14.3% vs PO")).toBeInTheDocument();
  });
  it("does not flag anything while vision is still counting", () => {
    render(<FourMatchStrip values={{ po: 14, grn: 14, invoice: 14, vision: 5 }} live />);
    expect(screen.queryByText("≠")).toBeNull();
  });
});
