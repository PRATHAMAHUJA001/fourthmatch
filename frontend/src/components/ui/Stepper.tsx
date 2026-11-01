import { cn } from "../../lib/cn";
import { SignalGlyph } from "./Glyph";

export interface Stage { key: string; label: string; short?: string; detail?: string }

export const PIPELINE_STAGES: Stage[] = [
  { key: "uploading", short: "Upload", label: "Upload", detail: "SHA-256 · Files API" },
  { key: "understanding", short: "Understand", label: "Understand video", detail: "muse-spark-1.3" },
  { key: "tracking", short: "Track", label: "Track objects", detail: "sam-3.1" },
  { key: "damage_check", short: "Damage", label: "Check damage", detail: "muse-spark-1.3" },
  { key: "reconciling", short: "Reconcile", label: "Reconcile", detail: "Python · 4-way match" },
  { key: "applying_policy", short: "Policy", label: "Apply policy", detail: "Decision agent" },
  { key: "verdict", short: "Verdict", label: "Verdict", detail: "Python recompute" },
];

/** Optional stage: only shown when the delivery carries a storekeeper voice remark. */
export const REMARK_STAGE: Stage = {
  key: "transcribing_remark", short: "Remark", label: "Transcribe remark", detail: "muse-voice-transcribe-1.0",
};

/** Pipeline stages for a job: inserts the remark stage after upload when the job has one. */
export function stagesFor(hasRemark: boolean): Stage[] {
  if (!hasRemark) return PIPELINE_STAGES;
  return [PIPELINE_STAGES[0], REMARK_STAGE, ...PIPELINE_STAGES.slice(1)];
}

export type StageState = "pending" | "active" | "done" | "failed";

/** Pipeline stepper. `states` maps stage key to state; `timing` maps key to ms. */
export function Stepper({ stages = PIPELINE_STAGES, states, timing, orientation = "vertical", className }: {
  stages?: Stage[]; states: Record<string, StageState>; timing?: Record<string, number>; orientation?: "vertical" | "horizontal"; className?: string;
}) {
  if (orientation === "horizontal") {
    return (
      <ol className={cn("flex items-center gap-1", className)} aria-label="Pipeline progress">
        {stages.map((s, i) => {
          const st = states[s.key] ?? "pending";
          return (
            <li key={s.key} className="flex min-w-0 flex-1 flex-col gap-1.5" aria-current={st === "active" ? "step" : undefined}>
              <span className={cn("h-[3px] rounded-full", st === "done" && "bg-fm-verified", st === "active" && "fm-live-dot bg-fm-hold", st === "failed" && "bg-fm-fraud", st === "pending" && "bg-fm-border")} />
              <span className={cn("truncate font-cond text-[10.5px] font-semibold uppercase tracking-[0.06em]", st === "pending" ? "text-fm-faint" : st === "active" ? "text-fm-hold" : "text-fm-muted")}>
                <span className="mr-1 font-mono text-fm-faint">{i + 1}</span>{s.label}
              </span>
            </li>
          );
        })}
      </ol>
    );
  }
  return (
    <ol className={cn("flex flex-col", className)} aria-label="Pipeline progress">
      {stages.map((s, i) => {
        const st = states[s.key] ?? "pending";
        const last = i === stages.length - 1;
        return (
          <li key={s.key} className="relative flex gap-3 pb-3 last:pb-0" aria-current={st === "active" ? "step" : undefined}>
            {!last && <span className={cn("absolute left-[7px] top-[18px] bottom-0 w-px", st === "done" ? "bg-fm-verified-line" : "bg-fm-border")} aria-hidden />}
            <span className={cn("relative z-10 mt-[2px] flex h-[15px] w-[15px] items-center justify-center",
              st === "done" && "text-fm-verified", st === "active" && "text-fm-hold", st === "failed" && "text-fm-fraud", st === "pending" && "text-fm-border-strong")}>
              {st === "done" ? <SignalGlyph signal="verified" size={13} /> : st === "active" ? <SignalGlyph signal="live" size={15} /> : st === "failed" ? <SignalGlyph signal="fraud" size={13} /> : <SignalGlyph signal="neutral" size={13} />}
            </span>
            <div className="flex min-w-0 flex-1 items-baseline justify-between gap-2">
              <div className="min-w-0">
                <div className={cn("text-[12.5px] font-medium", st === "pending" && "text-fm-faint", st === "active" && "text-fm-hold")}>{s.label}</div>
                {s.detail && <div className="truncate font-mono text-[10.5px] text-fm-faint">{s.detail}</div>}
              </div>
              <span className="shrink-0 font-mono text-[11px] tabular-nums text-fm-muted">
                {timing?.[s.key] != null ? `${(timing[s.key] / 1000).toFixed(1)}s` : st === "active" ? "…" : ""}
              </span>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
