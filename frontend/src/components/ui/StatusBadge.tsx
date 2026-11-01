import { CheckCircle2, Eye, PauseCircle, ShieldAlert, Split, CircleHelp } from "lucide-react";
import { cn } from "../../lib/cn";
import type { EvidenceQuality, Verdict } from "../../types/api";
import { VERDICT_LABEL } from "../../types/api";

const VERDICT_META: Record<Verdict, { icon: typeof CheckCircle2; classes: string; dot: string }> = {
  approve: { icon: CheckCircle2, classes: "text-fm-verified border-fm-verified/40 bg-fm-verified-bg", dot: "bg-fm-verified" },
  partial_pay: { icon: Split, classes: "text-fm-hold border-fm-hold/40 bg-fm-hold-bg", dot: "bg-fm-hold" },
  hold: { icon: PauseCircle, classes: "text-fm-hold border-fm-hold/40 bg-fm-hold-bg", dot: "bg-fm-hold" },
  human_review: { icon: Eye, classes: "text-fm-review border-fm-review/40 bg-fm-review-bg", dot: "bg-fm-review" },
};

const QUALITY_META: Record<EvidenceQuality, { icon: typeof CheckCircle2; label: string; classes: string }> = {
  reliable: { icon: CheckCircle2, label: "Evidence reliable", classes: "text-fm-verified border-fm-verified/40 bg-fm-verified-bg" },
  insufficient: { icon: CircleHelp, label: "Evidence insufficient", classes: "text-fm-review border-fm-review/40 bg-fm-review-bg" },
};

interface StatusBadgeProps {
  verdict?: Verdict;
  quality?: EvidenceQuality;
  fraud?: boolean;
  label?: string;
  pulse?: boolean;
  className?: string;
}

export function StatusBadge({ verdict, quality, fraud, label, pulse, className }: StatusBadgeProps) {
  if (fraud) {
    return (
      <span className={cn("inline-flex items-center gap-1.5 rounded-fm-sm border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-[0.04em] text-fm-fraud border-fm-fraud/40 bg-fm-fraud-bg", className)}>
        <ShieldAlert size={13} strokeWidth={2.2} aria-hidden />
        {label ?? "Fraud risk"}
      </span>
    );
  }
  if (quality) {
    const M = QUALITY_META[quality];
    const Icon = M.icon;
    return (
      <span className={cn("inline-flex items-center gap-1.5 rounded-fm-sm border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-[0.04em]", M.classes, className)}>
        <Icon size={13} strokeWidth={2.2} aria-hidden />
        {label ?? M.label}
      </span>
    );
  }
  const v: Verdict = verdict ?? "human_review";
  const M = VERDICT_META[v];
  const Icon = M.icon;
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-fm-sm border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-[0.04em]", M.classes, className)}>
      {pulse ? <span className={cn("fm-live-dot h-1.5 w-1.5 rounded-full", M.dot)} aria-hidden /> : <Icon size={13} strokeWidth={2.2} aria-hidden />}
      {label ?? VERDICT_LABEL[v]}
    </span>
  );
}
