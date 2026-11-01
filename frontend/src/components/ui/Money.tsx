import { cn } from "../../lib/cn";
import { formatINR, formatQty } from "../../lib/format";

export function Money({ paise, className, muted }: { paise: number; className?: string; muted?: boolean }) {
  return (
    <span className={cn("font-mono tabular-nums tracking-tight", muted && "text-fm-muted", className)}>
      {formatINR(paise)}
    </span>
  );
}

export function Qty({ value, unit, className }: { value: number; unit?: string; className?: string }) {
  return (
    <span className={cn("font-mono tabular-nums tracking-tight", className)}>
      {formatQty(value, unit)}
    </span>
  );
}
