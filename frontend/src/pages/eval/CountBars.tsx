import type { EvalCountRow } from "../../types/api";
import { cn } from "../../lib/cn";

/** Two thin bars per row: ground-truth count vs SAM-observed count. */
export function CountBars({ rows }: { rows: EvalCountRow[] }) {
  const max = Math.max(1, ...rows.flatMap((r) => [r.true_count, r.observed_count]));
  return (
    <div className="border-b border-fm-border px-4 pb-5 pt-2">
      <div className="mb-4 flex flex-wrap items-center gap-x-5 gap-y-1 text-[12px] text-fm-muted">
        <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-fm-faint" />True</span>
        <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-fm-verified-fill" />Observed</span>
        <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-fm-fraud-fill" />Observed, off</span>
      </div>
      <ul className="grid gap-x-10 gap-y-3 md:grid-cols-2">
        {rows.map((r) => {
          const ok = r.result === "PASS";
          return (
            <li key={`${r.scenario}-${r.category}`} className="grid grid-cols-[minmax(0,148px)_1fr_40px] items-center gap-3">
              <span className="truncate font-mono text-[12px] text-fm-muted" title={`${r.scenario} · ${r.category}`}>{r.scenario}</span>
              <span className="flex flex-col gap-1" aria-hidden>
                <span className="h-1.5 rounded-full bg-fm-faint/60" style={{ width: `${(r.true_count / max) * 100}%` }} />
                <span className={cn("h-1.5 rounded-full", ok ? "bg-fm-verified-fill" : "bg-fm-fraud-fill")} style={{ width: `${(r.observed_count / max) * 100}%` }} />
              </span>
              <span className="text-right font-mono text-[12px] tabular-nums text-fm-muted">{r.true_count}/{r.observed_count}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
