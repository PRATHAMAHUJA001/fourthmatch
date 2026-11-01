import { cn } from "../../lib/cn";
import type { EvidenceQuality, Verdict } from "../../types/api";
import { VERDICT_LABEL } from "../../types/api";
import { SignalGlyph, type Signal } from "./Glyph";

export const VERDICT_SIGNAL: Record<Verdict, Signal> = {
  approve: "verified", partial_pay: "partial", hold: "hold", human_review: "review",
};
export const SIGNAL_TONE: Record<Signal, string> = {
  verified: "text-fm-verified bg-fm-verified-bg border-fm-verified-line",
  hold: "text-fm-hold bg-fm-hold-bg border-fm-hold-line",
  partial: "text-fm-hold bg-fm-hold-bg border-fm-hold-line",
  review: "text-fm-review bg-fm-review-bg border-fm-review-line",
  fraud: "text-fm-fraud bg-fm-fraud-bg border-fm-fraud-line",
  neutral: "text-fm-muted bg-fm-raised border-fm-border",
  live: "text-fm-info bg-fm-info-bg border-fm-border",
};

interface StatusBadgeProps {
  verdict?: Verdict | null;
  quality?: EvidenceQuality;
  fraud?: boolean;
  signal?: Signal;
  label?: string;
  size?: "sm" | "md" | "lg";
  className?: string;
}

const SIZE = {
  sm: "h-5 gap-1 px-1.5 text-[10px]",
  md: "h-[22px] gap-1.5 px-2 text-[11px]",
  lg: "h-8 gap-2 px-3 text-[13px]",
};

/** Verdict / evidence / risk badge. Never colour alone: glyph shape + text label. */
export function StatusBadge({ verdict, quality, fraud, signal, label, size = "md", className }: StatusBadgeProps) {
  let s: Signal;
  let text: string;
  if (fraud) { s = "fraud"; text = label ?? "Fraud risk"; }
  else if (quality) { s = quality === "reliable" ? "verified" : "review"; text = label ?? (quality === "reliable" ? "Evidence reliable" : "Evidence insufficient"); }
  else if (signal) { s = signal; text = label ?? signal; }
  else if (verdict) { s = VERDICT_SIGNAL[verdict]; text = label ?? VERDICT_LABEL[verdict]; }
  else { s = "neutral"; text = label ?? "Not decided"; }
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center whitespace-nowrap rounded-fm-sm border font-cond font-semibold uppercase leading-none tracking-[0.06em]",
        SIZE[size], SIGNAL_TONE[s], className,
      )}
    >
      <SignalGlyph signal={s} size={size === "lg" ? 14 : size === "sm" ? 9 : 11} />
      {text}
    </span>
  );
}
