import type { ReactNode } from "react";
import { cn } from "../../lib/cn";

/** Small mono chip for IDs, clauses, model names. */
export function Tag({ children, tone = "neutral", className, title }: {
  children: ReactNode; tone?: "neutral" | "hold" | "verified" | "fraud" | "review" | "info" | "solid"; className?: string; title?: string;
}) {
  const tones = {
    neutral: "border-fm-border bg-fm-raised text-fm-muted",
    hold: "border-fm-hold-line bg-fm-hold-bg text-fm-hold",
    verified: "border-fm-verified-line bg-fm-verified-bg text-fm-verified",
    fraud: "border-fm-fraud-line bg-fm-fraud-bg text-fm-fraud",
    review: "border-fm-review-line bg-fm-review-bg text-fm-review",
    info: "border-fm-border bg-fm-info-bg text-fm-info",
    solid: "border-fm-text bg-fm-text text-fm-bg",
  };
  return (
    <span title={title} className={cn("inline-flex h-5 shrink-0 items-center gap-1 whitespace-nowrap rounded-fm-sm border px-1.5 font-mono text-[10.5px] font-medium leading-none", tones[tone], className)}>
      {children}
    </span>
  );
}

export function Kbd({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <kbd className={cn("inline-flex h-[18px] min-w-[18px] items-center justify-center rounded-[3px] border border-fm-border-strong bg-fm-raised px-1 font-mono text-[10px] font-medium text-fm-muted", className)}>
      {children}
    </kbd>
  );
}
