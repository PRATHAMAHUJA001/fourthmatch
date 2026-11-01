import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PIPELINE_STAGES, progressIndex, Stepper, type StageState } from "../src/components/ui/Stepper";

const st = (o: Record<string, StageState>) => o;

describe("Stepper (horizontal)", () => {
  it("renders one stop per stage, none current when idle, progress at zero", () => {
    const { container } = render(<Stepper states={{}} />);
    expect(screen.getAllByRole("listitem")).toHaveLength(PIPELINE_STAGES.length);
    expect(container.querySelector("[aria-current]")).toBeNull();
    expect(container.firstElementChild?.getAttribute("data-progress")).toBe("-1");
    expect(screen.getByTestId("stepper-progress").style.transform).toBe("scaleX(0)");
  });

  it("advances to the active stage, marks it current, and shows measured durations only", () => {
    const states = st({ uploading: "done", understanding: "done", tracking: "active" });
    const { container } = render(<Stepper states={states} timing={{ uploading: 1400, understanding: 2200 }} />);
    expect(container.querySelector("[aria-current='step']")?.textContent).toContain("Track objects");
    expect(screen.getByTestId("stepper-progress").style.transform).toBe(`scaleX(${2 / 6})`);
    expect(screen.getByText("1.4s")).toBeInTheDocument();
    expect(screen.getByText("2.2s")).toBeInTheDocument();
    expect(screen.getAllByText(/^\d+\.\ds$/)).toHaveLength(2);
  });

  it("parks on the last stage when everything is done, and flags failures", () => {
    const all = Object.fromEntries(PIPELINE_STAGES.map((s) => [s.key, "done" as StageState]));
    expect(progressIndex(PIPELINE_STAGES, all)).toBe(6);
    expect(progressIndex(PIPELINE_STAGES, st({ uploading: "done", understanding: "failed" }))).toBe(1);
    render(<Stepper states={st({ uploading: "done", understanding: "failed" })} />);
    expect(screen.getByText("failed")).toBeInTheDocument();
  });
});
