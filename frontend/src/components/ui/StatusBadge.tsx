import { cn } from "../../lib/cn";
import type { EvidenceQuality, Verdict } from "../../types/api";
import { VERDICT_LABEL } from "../../types/api";
import { SignalGlyph, type Signal } from "./Glyph";

export const VERDICT_SIGNAL: Record<Verdict, Signal> = {
  approve: "verified", partial_pay: "partial", hold: "hold", human_review: "review",
};
export const SIGNAL_TONE: Record<Signal, string> = {
  verified: "text-fm-verified bg-fm-verified-bg",
  hold: "text-fm-hold bg-fm-hold-bg",
  partial: "text-fm-hold bg-fm-hold-bg",
  review: "text-fm-review bg-fm-review-bg",
  fraud: "text-fm-fraud bg-fm-fraud-bg",
  neutral: "text-fm-muted bg-fm-raised",
  live: "text-fm-info bg-fm-info-bg",
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
  sm: "h-[22px] gap-1 pl-1.5 pr-2 text-[11.5px]",
  md: "h-6 gap-1.5 pl-2 pr-2.5 text-[12.5px]",
  lg: "h-9 gap-2 pl-3 pr-4 text-[15px]",
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
        "inline-flex shrink-0 items-center whitespace-nowrap rounded-full font-semibold leading-none tracking-[-0.01em]",
        SIZE[size], SIGNAL_TONE[s], className,
      )}
    >
      <SignalGlyph signal={s} size={size === "lg" ? 15 : size === "sm" ? 11 : 12} />
      {text}
    </span>
  );
}
