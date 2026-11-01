/** Route-style pipeline progress: a track with one stop per stage and a small truck that
 *  travels to the active stop. Completed segment is solid, pending is dashed. Durations
 *  come from measured timings only; nothing is shown for a stage that has not run. */
import { cn } from "../../lib/cn";
import { PIPELINE_STAGES, type Stage, type StageState } from "./Stepper";

/** Index of the stop the truck sits at: the active stage, else the last finished one, else 0. Pure. */
export function truckStop(stages: Stage[], states: Record<string, StageState>): number {
  let active = -1, done = -1;
  stages.forEach((s, i) => {
    const st = states[s.key];
    if (st === "active" || st === "failed") active = i;
    if (st === "done") done = i;
  });
  return Math.max(0, active >= 0 ? active : done);
}

function TruckGlyph({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 40 20" width="34" height="17" className={className} fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" strokeLinecap="round" aria-hidden>
      <rect x="1" y="2" width="24" height="12" rx="1" />
      <path d="M26 6h6l5 5v3h-11z" />
      <path d="M1 14h36" />
      <circle cx="9" cy="16" r="2.6" fill="var(--fm-panel)" />
      <circle cx="19" cy="16" r="2.6" fill="var(--fm-panel)" />
      <circle cx="31" cy="16" r="2.6" fill="var(--fm-panel)" />
    </svg>
  );
}

export function RouteProgress({ stages = PIPELINE_STAGES, states, timing, className }: {
  stages?: Stage[]; states: Record<string, StageState>; timing?: Record<string, number>; className?: string;
}) {
  const n = stages.length;
  const at = truckStop(stages, states);
  const frac = n > 1 ? at / (n - 1) : 0;
  const failed = stages.some((s) => states[s.key] === "failed");
  const halfCol = 100 / (2 * n);
  return (
    <div className={cn("relative", className)} data-truck-stop={at}>
      {/* track area spans stop centre to stop centre */}
      <div className="pointer-events-none absolute top-0 h-[44px]" style={{ left: `${halfCol}%`, right: `${halfCol}%` }} aria-hidden>
        <div className="absolute inset-x-0 bottom-[7px] border-t-[1.5px] border-dashed border-fm-border-strong" />
        <div
          className="absolute inset-x-0 bottom-[7px] h-[1.5px] origin-left bg-fm-verified transition-transform duration-200 ease-[var(--fm-ease)] motion-reduce:transition-none"
          style={{ transform: `scaleX(${frac})` }}
        />
        <div
          className="absolute bottom-[10px] left-0 w-full transition-transform duration-200 ease-[var(--fm-ease)] motion-reduce:transition-none"
          style={{ transform: `translateX(${frac * 100}%)` }}
          data-testid="route-truck"
        >
          <TruckGlyph className={cn("-translate-x-1/2", failed ? "text-fm-fraud" : "text-fm-hold")} />
        </div>
      </div>
      <ol className="relative grid pt-[44px]" style={{ gridTemplateColumns: `repeat(${n}, minmax(0, 1fr))` }} aria-label="Pipeline progress">
        {stages.map((s, i) => {
          const st = states[s.key] ?? "pending";
          const ms = timing?.[s.key];
          return (
            <li key={s.key} className="flex min-w-0 flex-col items-center gap-1 text-center" aria-current={st === "active" ? "step" : undefined} data-state={st}>
              <span
                className={cn(
                  "-mt-[11px] mb-1 block h-[9px] w-[9px] rounded-full border-[1.5px] bg-fm-panel",
                  st === "done" && "border-fm-verified bg-fm-verified",
                  st === "active" && "fm-live-dot border-fm-hold bg-fm-hold",
                  st === "failed" && "border-fm-fraud bg-fm-fraud",
                  st === "pending" && "border-fm-border-strong",
                )}
                aria-hidden
              />
              <span className={cn("w-full truncate font-cond text-[10.5px] font-semibold uppercase tracking-[0.06em] max-sm:text-[9px] max-sm:tracking-normal", st === "pending" ? "text-fm-faint" : st === "active" ? "text-fm-hold" : st === "failed" ? "text-fm-fraud" : "text-fm-muted")}>
                <span className="mr-1 font-mono text-fm-faint max-sm:hidden">{i + 1}</span>{s.short ?? s.label}
              </span>
              <span className="h-[14px] font-mono text-[10.5px] tabular-nums text-fm-muted">
                {ms != null ? `${(ms / 1000).toFixed(1)}s` : st === "active" ? "…" : st === "failed" ? "failed" : ""}
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
