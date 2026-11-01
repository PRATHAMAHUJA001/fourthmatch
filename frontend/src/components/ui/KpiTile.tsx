import type { ReactNode } from "react";
import { cn } from "../../lib/cn";
import { SignalGlyph, type Signal } from "./Glyph";

type Tone = "hold" | "verified" | "fraud" | "review" | "neutral";
const TONE_TEXT: Record<Tone, string> = {
  hold: "text-fm-hold", verified: "text-fm-verified", fraud: "text-fm-fraud", review: "text-fm-review", neutral: "text-fm-text",
};
const TONE_SIGNAL: Record<Tone, Signal> = { hold: "hold", verified: "verified", fraud: "fraud", review: "review", neutral: "neutral" };

interface KpiTileProps {
  label: string;
  value: ReactNode;
  unit?: string;
  delta?: ReactNode;
  tone?: Tone;
  hint?: ReactNode;
  spark?: number[];
  className?: string;
}

/** Readout: a large figure first, then what it is, then one quiet line of context. */
export function KpiTile({ label, value, unit, delta, tone = "neutral", hint, spark, className }: KpiTileProps) {
  return (
    <div className={cn("relative flex min-w-0 flex-col px-7 py-6 max-sm:px-5 max-sm:py-5", className)}>
      <div className="flex items-end justify-between gap-3">
        <div className={cn("fm-figure min-w-0 whitespace-nowrap text-[clamp(30px,3vw,44px)] leading-none max-sm:text-[26px]", TONE_TEXT[tone])}>
          {value}
          {unit && <span className="ml-1.5 font-sans text-[17px] font-medium tracking-[-0.01em] text-fm-faint max-sm:text-[13px]">{unit}</span>}
        </div>
        {spark && spark.length > 1 && <Spark values={spark} className={cn("mb-1 max-md:hidden", tone === "neutral" ? "text-fm-faint" : TONE_TEXT[tone])} />}
      </div>
      <div className="mt-3 flex items-center gap-1.5 text-[15px] font-semibold tracking-[-0.014em]">
        {tone !== "neutral" && <SignalGlyph signal={TONE_SIGNAL[tone]} size={12} className={TONE_TEXT[tone]} />}
        <span className="truncate">{label}</span>
      </div>
      {(delta || hint) && (
        <div className="mt-0.5 flex items-center gap-2 text-[13px] text-fm-muted">
          {delta && <span className="font-mono tabular-nums">{delta}</span>}
          {hint && <span className="truncate">{hint}</span>}
        </div>
      )}
    </div>
  );
}

/** A white card of readouts divided by hairlines. */
export function KpiStrip({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("grid divide-fm-border overflow-hidden rounded-fm bg-fm-panel max-md:divide-y md:divide-x", className)}>
      {children}
    </div>
  );
}

export function Spark({ values, className, width = 80, height = 28 }: { values: number[]; className?: string; width?: number; height?: number }) {
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const step = width / (values.length - 1);
  const pts = values.map((v, i) => `${(i * step).toFixed(1)},${(height - ((v - min) / (max - min || 1)) * (height - 4) - 2).toFixed(1)}`);
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className={cn("shrink-0 overflow-visible", className)} aria-hidden>
      <polyline points={pts.join(" ")} fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={width} cy={pts[pts.length - 1].split(",")[1]} r="2.5" fill="currentColor" />
    </svg>
  );
}
