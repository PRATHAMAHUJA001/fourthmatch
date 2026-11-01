import type { EvalCountRow } from "../../types/api";
import { cn } from "../../lib/cn";

/** Two thin bars per row: ground-truth count vs SAM-observed count. */
export function CountBars({ rows }: { rows: EvalCountRow[] }) {
  const max = Math.max(1, ...rows.flatMap((r) => [r.true_count, r.observed_count]));
  return (
    <div className="border-b border-fm-border px-3 py-3">
      <div className="mb-2 flex items-center gap-4 font-mono text-[10.5px] text-fm-muted">
        <span className="flex items-center gap-1.5"><span className="h-[3px] w-4 bg-fm-muted" />true</span>
        <span className="flex items-center gap-1.5"><span className="h-[3px] w-4 bg-fm-verified" />observed</span>
        <span className="flex items-center gap-1.5"><span className="h-[3px] w-4 bg-fm-fraud" />observed, off</span>
      </div>
      <ul className="grid gap-x-8 gap-y-1.5 md:grid-cols-2">
        {rows.map((r) => {
          const ok = r.result === "PASS";
          return (
            <li key={`${r.scenario}-${r.category}`} className="grid grid-cols-[minmax(0,148px)_1fr_40px] items-center gap-3">
              <span className="truncate font-mono text-[10.5px] text-fm-muted" title={`${r.scenario} · ${r.category}`}>{r.scenario}</span>
              <span className="flex flex-col gap-[3px]" aria-hidden>
                <span className="h-[3px] bg-fm-muted" style={{ width: `${(r.true_count / max) * 100}%` }} />
                <span className={cn("h-[3px]", ok ? "bg-fm-verified" : "bg-fm-fraud")} style={{ width: `${(r.observed_count / max) * 100}%` }} />
              </span>
              <span className="text-right font-mono text-[10.5px] tabular-nums text-fm-muted">{r.true_count}/{r.observed_count}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
