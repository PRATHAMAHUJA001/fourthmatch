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
  it("hides the remark stage when the upload had no remark", () => {
    const d = derive([ev(1, "queued", { has_remark: false }), ev(2, "uploading")], [0, 5]);
    expect(d.stages.map((s) => s.key)).not.toContain("transcribing_remark");
  });
  it("shows the remark stage after upload when the upload carried one", () => {
    const d = derive([
      ev(1, "queued", { has_remark: true }), ev(2, "uploading"), ev(3, "uploading_finished"),
      ev(4, "transcribing_remark"), ev(5, "transcribing_remark_finished"), ev(6, "understanding"),
    ], [0, 1, 2, 3, 7, 8]);
    expect(d.stages.map((s) => s.key).slice(0, 3)).toEqual(["uploading", "transcribing_remark", "understanding"]);
    expect(d.states.transcribing_remark).toBe("done");
    expect(d.timing.transcribing_remark).toBe(4);
    expect(d.states.understanding).toBe("active");
  });
  it("keeps a failed remark stage failed while the pipeline carries on to done", () => {
    const d = derive([
      ev(1, "queued", { has_remark: true }), ev(2, "transcribing_remark"), ev(3, "transcribing_remark_failed"),
      ev(4, "understanding"), ev(5, "done"),
    ], [0, 1, 2, 3, 4]);
    expect(d.states.transcribing_remark).toBe("failed");
    expect(d.states.understanding).toBe("done");
    expect(d.failed).toBe(false);
  });
});
