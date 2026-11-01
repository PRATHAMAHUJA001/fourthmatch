import { cn } from "../../lib/cn";
import { formatINR, formatQty } from "../../lib/format";

/** Rupees from integer paise, en-IN grouping (12,45,000). Always mono + tabular. */
export function Money({ paise, className, muted, sign }: { paise: number; className?: string; muted?: boolean; sign?: boolean }) {
  return (
    <span className={cn("font-mono tabular-nums tracking-tight", muted && "text-fm-muted", paise === 0 && "text-fm-faint", className)}>
      {formatINR(paise, { sign })}
    </span>
  );
}

export function Qty({ value, unit, className }: { value: number | null; unit?: string; className?: string }) {
  if (value === null) return <span className={cn("font-mono text-fm-faint", className)}>—</span>;
  return (
    <span className={cn("font-mono tabular-nums tracking-tight", className)}>
      {formatQty(value)}
      {unit && <span className="ml-1 text-[0.85em] text-fm-faint">{unit}</span>}
    </span>
  );
}
