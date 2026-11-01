import type { ReactNode } from "react";
import { cn } from "../../lib/cn";

/** Small mono chip for IDs, clauses, model names. */
export function Tag({ children, tone = "neutral", className, title }: {
  children: ReactNode; tone?: "neutral" | "hold" | "verified" | "fraud" | "review" | "info" | "solid"; className?: string; title?: string;
}) {
  const tones = {
    neutral: "bg-fm-raised text-fm-muted",
    hold: "bg-fm-hold-bg text-fm-hold",
    verified: "bg-fm-verified-bg text-fm-verified",
    fraud: "bg-fm-fraud-bg text-fm-fraud",
    review: "bg-fm-review-bg text-fm-review",
    info: "bg-fm-info-bg text-fm-info",
    solid: "bg-fm-text text-fm-canvas",
  };
  return (
    <span title={title} className={cn("inline-flex h-[22px] shrink-0 items-center gap-1 whitespace-nowrap rounded-full px-2 font-mono text-[11px] font-medium leading-none", tones[tone], className)}>
      {children}
    </span>
  );
}

export function Kbd({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <kbd className={cn("inline-flex h-5 min-w-5 items-center justify-center rounded-[6px] bg-fm-raised px-1.5 font-sans text-[11px] font-medium text-fm-muted shadow-[inset_0_-1px_0_var(--fm-border-strong)]", className)}>
      {children}
    </kbd>
  );
}
