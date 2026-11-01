import { Check } from "lucide-react";
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

/** Index the progress line reaches: the active (or failed) stage, else the last finished one,
 *  else -1 when nothing has started. Pure; unit-tested. */
export function progressIndex(stages: Stage[], states: Record<string, StageState>): number {
  let active = -1, done = -1;
  stages.forEach((s, i) => {
    const st = states[s.key];
    if (st === "active" || st === "failed") active = i;
    if (st === "done") done = i;
  });
  return active >= 0 ? active : done;
}

const secs = (ms: number) => `${(ms / 1000).toFixed(1)}s`;

function Dot({ st }: { st: StageState }) {
  return (
    <span
      className={cn(
        "relative z-10 flex h-[22px] w-[22px] items-center justify-center rounded-full transition-colors duration-300",
        st === "done" && "bg-fm-text text-fm-canvas",
        st === "active" && "bg-fm-panel shadow-[inset_0_0_0_2px_var(--fm-accent)]",
        st === "failed" && "bg-fm-panel text-fm-fraud",
        st === "pending" && "bg-fm-panel shadow-[inset_0_0_0_1.5px_var(--fm-border-strong)]",
      )}
      aria-hidden
    >
      {st === "done" && <Check size={12} strokeWidth={3} />}
      {st === "active" && <span className="fm-live-dot h-2 w-2 rounded-full bg-fm-accent" />}
      {st === "failed" && <SignalGlyph signal="fraud" size={14} />}
    </span>
  );
}

/** Pipeline stepper. `states` maps stage key to state; `timing` maps key to measured ms.
 *  Durations appear only for stages that actually ran. */
export function Stepper({ stages = PIPELINE_STAGES, states, timing, orientation = "horizontal", className }: {
  stages?: Stage[]; states: Record<string, StageState>; timing?: Record<string, number>; orientation?: "vertical" | "horizontal"; className?: string;
}) {
  if (orientation === "horizontal") {
    const n = stages.length;
    const at = progressIndex(stages, states);
    const frac = n > 1 ? Math.max(0, at) / (n - 1) : 0;
    const half = 100 / (2 * n);
    const current = at >= 0 ? stages[at] : null;
    const curState = current ? states[current.key] : undefined;
    return (
      <div className={cn("relative", className)} data-progress={at}>
        <div className="pointer-events-none absolute top-[10px] h-[2px]" style={{ left: `${half}%`, right: `${half}%` }} aria-hidden>
          <div className="absolute inset-0 rounded-full bg-fm-hover" />
          <div className="absolute inset-0 origin-left rounded-full bg-fm-text transition-transform duration-500 ease-[var(--fm-ease)] motion-reduce:transition-none" style={{ transform: `scaleX(${frac})` }} data-testid="stepper-progress" />
        </div>
        <ol className="relative grid" style={{ gridTemplateColumns: `repeat(${n}, minmax(0, 1fr))` }} aria-label="Pipeline progress">
          {stages.map((s) => {
            const st = states[s.key] ?? "pending";
            const ms = timing?.[s.key];
            return (
              <li key={s.key} className="flex min-w-0 flex-col items-center text-center" aria-current={st === "active" ? "step" : undefined} data-state={st}>
                <Dot st={st} />
                <span className={cn("mt-3 w-full truncate px-1 text-[13px] font-semibold tracking-[-0.01em] max-md:sr-only", st === "pending" ? "text-fm-faint" : st === "active" ? "text-fm-accent-text" : st === "failed" ? "text-fm-fraud" : "text-fm-text")}>
                  {s.label}
                </span>
                <span className="w-full truncate px-1 text-[12px] text-fm-faint max-md:hidden">{s.detail}</span>
                <span className="mt-0.5 h-[16px] font-mono text-[12px] tabular-nums text-fm-muted max-md:hidden">
                  {ms != null ? secs(ms) : st === "active" ? "…" : st === "failed" ? "failed" : ""}
                </span>
              </li>
            );
          })}
        </ol>
        <p className="mt-3 flex items-baseline justify-between gap-3 text-[14px] md:hidden" aria-hidden>
          <span className={cn("truncate font-semibold", curState === "active" ? "text-fm-accent-text" : curState === "failed" ? "text-fm-fraud" : "text-fm-text")}>
            {current ? current.label : "Queued"}
          </span>
          <span className="shrink-0 text-[12px] text-fm-muted">{current ? `${at + 1} of ${n}` : `0 of ${n}`}</span>
        </p>
      </div>
    );
  }
  return (
    <ol className={cn("flex flex-col", className)} aria-label="Pipeline progress">
      {stages.map((s, i) => {
        const st = states[s.key] ?? "pending";
        const last = i === stages.length - 1;
        return (
          <li key={s.key} className="relative flex gap-3 pb-5 last:pb-0" aria-current={st === "active" ? "step" : undefined}>
            {!last && <span className={cn("absolute left-[10px] top-[24px] bottom-0 w-[2px] rounded-full", st === "done" ? "bg-fm-text" : "bg-fm-hover")} aria-hidden />}
            <Dot st={st} />
            <div className="flex min-w-0 flex-1 items-baseline justify-between gap-2">
              <div className="min-w-0">
                <div className={cn("text-[14px] font-semibold tracking-[-0.01em]", st === "pending" && "text-fm-faint", st === "active" && "text-fm-accent-text", st === "failed" && "text-fm-fraud")}>{s.label}</div>
                {s.detail && <div className="truncate text-[12px] text-fm-faint">{s.detail}</div>}
              </div>
              <span className="shrink-0 font-mono text-[12px] tabular-nums text-fm-muted">
                {timing?.[s.key] != null ? secs(timing[s.key]) : st === "active" ? "…" : ""}
              </span>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
