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

/** Instrument readout: condensed label, big mono figure, one line of context. No card chrome. */
export function KpiTile({ label, value, unit, delta, tone = "neutral", hint, spark, className }: KpiTileProps) {
  return (
    <div className={cn("relative flex min-w-0 flex-col justify-between gap-2 px-4 py-3", className)}>
      <div className="flex items-center gap-1.5">
        {tone !== "neutral" && <SignalGlyph signal={TONE_SIGNAL[tone]} size={9} className={TONE_TEXT[tone]} />}
        <span className="fm-label truncate">{label}</span>
      </div>
      <div className="flex items-end justify-between gap-3">
        <div className={cn("min-w-0 font-mono text-[28px] font-medium leading-none tracking-[-0.03em] tabular-nums max-sm:text-[24px]", tone !== "neutral" && TONE_TEXT[tone])}>
          {value}
          {unit && <span className="ml-1 text-[13px] font-normal tracking-normal text-fm-faint">{unit}</span>}
        </div>
        {spark && spark.length > 1 && <Spark values={spark} className={cn("max-md:hidden", tone === "neutral" ? "text-fm-muted" : TONE_TEXT[tone])} />}
      </div>
      {(delta || hint) && (
        <div className="flex items-center gap-2 text-[11.5px] text-fm-muted">
          {delta && <span className="font-mono tabular-nums">{delta}</span>}
          {hint && <span className="truncate text-fm-faint">{hint}</span>}
        </div>
      )}
    </div>
  );
}

/** A strip of readouts separated by hairlines (the KPI rail). */
export function KpiStrip({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("grid divide-fm-border rounded-fm border border-fm-border bg-fm-panel max-md:divide-y md:divide-x", className)}>
      {children}
    </div>
  );
}

export function Spark({ values, className, width = 72, height = 24 }: { values: number[]; className?: string; width?: number; height?: number }) {
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const step = width / (values.length - 1);
  const pts = values.map((v, i) => `${(i * step).toFixed(1)},${(height - ((v - min) / (max - min || 1)) * (height - 2) - 1).toFixed(1)}`);
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className={cn("shrink-0", className)} aria-hidden>
      <polyline points={pts.join(" ")} fill="none" stroke="currentColor" strokeWidth="1.25" strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={width} cy={pts[pts.length - 1].split(",")[1]} r="2" fill="currentColor" />
    </svg>
  );
}
