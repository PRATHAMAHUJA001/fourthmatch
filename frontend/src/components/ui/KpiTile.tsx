import type { ReactNode } from "react";
import { cn } from "../../lib/cn";

type Tone = "hold" | "verified" | "fraud" | "review" | "neutral";

const TONE_BAR: Record<Tone, string> = {
  hold: "bg-fm-hold", verified: "bg-fm-verified", fraud: "bg-fm-fraud",
  review: "bg-fm-review", neutral: "bg-fm-border-strong",
};
const TONE_TEXT: Record<Tone, string> = {
  hold: "text-fm-hold", verified: "text-fm-verified", fraud: "text-fm-fraud",
  review: "text-fm-review", neutral: "text-fm-muted",
};

interface KpiTileProps {
  label: string;
  value: ReactNode;
  delta?: string;
  tone?: Tone;
  hint?: string;
  className?: string;
}

export function KpiTile({ label, value, delta, tone = "neutral", hint, className }: KpiTileProps) {
  return (
    <div className={cn("relative overflow-hidden rounded-fm border border-fm-border bg-fm-panel px-3 py-3", className)}>
      <span className={cn("absolute inset-y-0 left-0 w-[3px]", TONE_BAR[tone])} aria-hidden />
      <div className="text-[11px] font-medium uppercase tracking-[0.06em] text-fm-muted">{label}</div>
      <div className="mt-1 font-mono text-[22px] font-semibold leading-none tabular-nums tracking-tight">{value}</div>
      {(delta || hint) && (
        <div className="mt-1.5 flex items-center gap-2 text-[11px]">
          {delta && <span className={cn("font-mono tabular-nums", TONE_TEXT[tone])}>{delta}</span>}
          {hint && <span className="text-fm-faint">{hint}</span>}
        </div>
      )}
    </div>
  );
}
