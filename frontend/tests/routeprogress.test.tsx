import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RouteProgress, truckStop } from "../src/components/ui/RouteProgress";
import { PIPELINE_STAGES, type StageState } from "../src/components/ui/Stepper";

const st = (o: Record<string, StageState>) => o;

describe("RouteProgress", () => {
  it("renders all seven stops, none active when idle, truck at the start", () => {
    const { container } = render(<RouteProgress states={{}} />);
    expect(screen.getAllByRole("listitem")).toHaveLength(7);
    expect(container.querySelector("[aria-current]")).toBeNull();
    expect(container.firstElementChild?.getAttribute("data-truck-stop")).toBe("0");
    expect(screen.getByTestId("route-truck").style.transform).toBe("translateX(0%)");
  });

  it("moves the truck to the active stop and marks it current", () => {
    const states = st({ uploading: "done", understanding: "done", tracking: "active" });
    const { container } = render(<RouteProgress states={states} timing={{ uploading: 1400, understanding: 2200 }} />);
    expect(container.querySelector("[aria-current='step']")?.textContent).toContain("Track");
    expect(screen.getByTestId("route-truck").style.transform).toBe("translateX(33.33333333333333%)");
    expect(screen.getByText("1.4s")).toBeInTheDocument();
    expect(screen.getByText("2.2s")).toBeInTheDocument();
  });

  it("shows durations only for stages that were measured", () => {
    render(<RouteProgress states={st({ uploading: "done", understanding: "active" })} timing={{ uploading: 900 }} />);
    expect(screen.getAllByText(/^\d+\.\ds$/)).toHaveLength(1);
  });

  it("parks the truck on the last stop when everything is done, and flags failures", () => {
    const all = Object.fromEntries(PIPELINE_STAGES.map((s) => [s.key, "done" as StageState]));
    expect(truckStop(PIPELINE_STAGES, all)).toBe(6);
    expect(truckStop(PIPELINE_STAGES, st({ uploading: "done", understanding: "failed" }))).toBe(1);
    render(<RouteProgress states={st({ uploading: "done", understanding: "failed" })} />);
    expect(screen.getByText("failed")).toBeInTheDocument();
  });
});
