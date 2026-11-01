import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusBadge } from "../src/components/ui/StatusBadge";
import { Money } from "../src/components/ui/Money";

describe("StatusBadge — never colour alone", () => {
  it("renders label + icon for every verdict", () => {
    const cases = [
      ["approve", "Verified"],
      ["partial_pay", "Partial pay"],
      ["hold", "On hold"],
      ["human_review", "Needs review"],
    ] as const;
    for (const [verdict, label] of cases) {
      const { unmount } = render(<StatusBadge verdict={verdict} />);
      expect(screen.getByText(label)).toBeInTheDocument();
      unmount();
    }
  });
  it("renders fraud risk distinctly", () => {
    render(<StatusBadge fraud />);
    expect(screen.getByText("Fraud risk")).toBeInTheDocument();
  });
});

describe("Money", () => {
  it("renders Indian format", () => {
    render(<Money paise={124500000} />);
    expect(screen.getByText("₹12,45,000")).toBeInTheDocument();
  });
});
