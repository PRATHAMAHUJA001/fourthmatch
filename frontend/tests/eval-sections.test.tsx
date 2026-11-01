import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { evalResults } from "../src/mocks/dataset";
import { AgentPanel, CostPanel, ImageEvalPanel, NotMeasured } from "../src/pages/eval/Sections";
import type { EvalResults } from "../src/types/api";

const summary = { n: 0, measured: 0, correct: 0, accuracy: null, mean_abs_error: null };
const empty: EvalResults = {
  schema_version: 1, generated_at: "2026-11-01T00:00:00Z",
  videos: { rows: [], count_summary: summary, damage_summary: summary },
  images: { synthetic: true, images_total: 0, images_confirmed: 0, rows: [], summary },
  verdicts: { served: null, served_reason: "no approved policy rules", agent: null, agent_reason: "no stored agent decision" },
  latency: [],
  cost: { rates_configured: false, currency: null, deliveries_processed: 0, total_input_tokens: 0, total_output_tokens: 0, total_cost: null, cost_per_delivery: null, per_model: [] },
  not_measured: ["latency: no model_calls rows in the database"],
};

describe("Eval sections", () => {
  it("labels eval images SYNTHETIC and shows an empty state when none exist", () => {
    render(<ImageEvalPanel results={empty} />);
    expect(screen.getByText("SYNTHETIC")).toBeInTheDocument();
    expect(screen.getByText("No eval images yet")).toBeInTheDocument();
  });
  it("scores only confirmed images and shows a dash for a missing SAM count", () => {
    const r: EvalResults = {
      ...empty,
      images: {
        synthetic: true, images_total: 12, images_confirmed: 2,
        rows: [
          { id: "img01", file: "img01.png", phrase: "cardboard box", prompted_count: 3, sam_count: 3, true_count: 3, correct: true, synthetic: true },
          { id: "img02", file: "img02.png", phrase: "white sack", prompted_count: 4, sam_count: null, true_count: 5, correct: null, synthetic: true },
        ],
        summary: { n: 2, measured: 1, correct: 1, accuracy: 1, mean_abs_error: 0 },
      },
    };
    render(<ImageEvalPanel results={r} />);
    expect(screen.getByText("img01")).toBeInTheDocument();
    expect(screen.getByText(/have a human-confirmed/)).toBeInTheDocument();
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });
  it("shows a dash for unmeasured cost and the reason for the agent", () => {
    render(<><CostPanel results={empty} /><AgentPanel results={empty} /></>);
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText(/No prices are configured/)).toBeInTheDocument();
    expect(screen.getByText(/no stored agent decision/)).toBeInTheDocument();
  });
  it("lists what was not measured, and explains a missing report", () => {
    const { unmount } = render(<NotMeasured results={empty} />);
    expect(screen.getByText(/latency: no model_calls rows/)).toBeInTheDocument();
    unmount();
    render(<NotMeasured results={null} />);
    expect(screen.getByText(/scripts\/run_eval.py/)).toBeInTheDocument();
  });
  it("mock mode serves the committed eval report with video counts from the data file", () => {
    const d = evalResults();
    expect(d.results).not.toBeNull();
    expect(d.results?.images.synthetic).toBe(true);
    expect(d.results?.videos.rows.length).toBe(d.counts.length);
  });
});
