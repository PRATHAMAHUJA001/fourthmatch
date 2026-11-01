import { cn } from "../../lib/cn";

/** The FourthMatch mark: four bars. PO, GRN and invoice; the taller fourth (vision) is the signal. */
export function BrandMark({ size = 20, muted, className }: { size?: number; muted?: boolean; className?: string }) {
  const ink = muted ? "var(--fm-border-strong)" : "currentColor";
  return (
    <svg width={size} height={size} viewBox="0 0 20 20" className={cn("shrink-0", className)} aria-hidden>
      <rect x="1.5" y="5" width="2.8" height="10" rx="1.4" fill={ink} />
      <rect x="6.1" y="5" width="2.8" height="10" rx="1.4" fill={ink} />
      <rect x="10.7" y="5" width="2.8" height="10" rx="1.4" fill={ink} />
      <rect x="15.3" y="2" width="2.8" height="16" rx="1.4" fill={muted ? "var(--fm-faint)" : "var(--fm-hold-fill)"} />
    </svg>
  );
}

export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <BrandMark size={18} />
      <span className="text-[17px] font-semibold tracking-[-0.025em]">FourthMatch</span>
    </span>
  );
}
