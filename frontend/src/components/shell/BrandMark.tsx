import { cn } from "../../lib/cn";

/** The FourthMatch mark: four bars — PO, GRN, Invoice match; the fourth (vision) is the signal. */
export function BrandMark({ size = 20, muted, className }: { size?: number; muted?: boolean; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 20 20" className={cn("shrink-0", className)} aria-hidden>
      <rect x="1" y="4" width="3" height="12" rx="0.5" fill={muted ? "var(--fm-border-strong)" : "var(--fm-text)"} />
      <rect x="6" y="4" width="3" height="12" rx="0.5" fill={muted ? "var(--fm-border-strong)" : "var(--fm-text)"} />
      <rect x="11" y="4" width="3" height="12" rx="0.5" fill={muted ? "var(--fm-border-strong)" : "var(--fm-text)"} />
      <rect x="16" y="1" width="3" height="18" rx="0.5" fill={muted ? "var(--fm-faint)" : "var(--fm-hold)"} />
    </svg>
  );
}

export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <BrandMark size={18} />
      <span className="text-[14px] font-semibold tracking-[-0.02em]">
        Fourth<span className="text-fm-hold">Match</span>
      </span>
    </span>
  );
}
