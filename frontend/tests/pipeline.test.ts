import { describe, expect, it } from "vitest";
import { derive } from "../src/components/evidence/PipelineRun";
import type { JobEventRead } from "../src/types/api";

const ev = (seq: number, event_type: string, payload: Record<string, unknown> = {}): JobEventRead =>
  ({ id: seq, job_id: "j", seq, event_type, message: "", payload, created_at: "" });

describe("pipeline event derivation", () => {
  it("tracks stage state, timings and the live track counter from stored events", () => {
    const events = [
      ev(1, "uploading"), ev(2, "uploading_finished"),
      ev(3, "tracking"), ev(4, "tracking_progress", { po_line_id: 1, tracks: 3 }), ev(5, "tracking_progress", { po_line_id: 2, tracks: 2 }),
    ];
    const d = derive(events, [0, 900, 1000, 1200, 1300]);
    expect(d.states.uploading).toBe("done");
    expect(d.timing.uploading).toBe(900);
    expect(d.states.tracking).toBe("active");
    expect(d.tracks).toBe(5);
  });
  it("marks every stage done on done and reads the verdict payload", () => {
    const d = derive([ev(1, "verdict", { verdict: "hold", held_paise: 100 }), ev(2, "done")], [0, 10]);
    expect(d.verdict).toEqual({ verdict: "hold", held_paise: 100 });
    expect(Object.values(d.states).every((s) => s === "done")).toBe(true);
  });
  it("marks the active stage failed on failure", () => {
    const d = derive([ev(1, "tracking"), ev(2, "failed")], [0, 5]);
    expect(d.states.tracking).toBe("failed");
  });
});
