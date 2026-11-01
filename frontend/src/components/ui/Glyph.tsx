/** Signal glyphs: each state has its own SHAPE so meaning survives greyscale,
 *  colour-blindness and projectors. Always rendered next to a text label. */
import type { SVGProps } from "react";

export type Signal = "verified" | "hold" | "partial" | "review" | "fraud" | "neutral" | "live";

export function SignalGlyph({ signal, size = 12, ...rest }: { signal: Signal; size?: number } & SVGProps<SVGSVGElement>) {
  const common = { width: size, height: size, viewBox: "0 0 12 12", "aria-hidden": true, ...rest };
  switch (signal) {
    case "verified": // filled square with check
      return (
        <svg {...common}><rect x="0.5" y="0.5" width="11" height="11" rx="2" fill="currentColor" /><path d="M3.2 6.2 5.1 8l3.7-4" stroke="var(--fm-ink)" strokeWidth="1.6" fill="none" strokeLinecap="round" strokeLinejoin="round" /></svg>
      );
    case "hold": // diamond with pause bars
      return (
        <svg {...common}><path d="M6 0.6 11.4 6 6 11.4 0.6 6Z" fill="currentColor" /><path d="M4.9 4.3v3.4M7.1 4.3v3.4" stroke="var(--fm-ink)" strokeWidth="1.3" strokeLinecap="round" /></svg>
      );
    case "partial": // half-filled circle
      return (
        <svg {...common}><circle cx="6" cy="6" r="5" fill="none" stroke="currentColor" strokeWidth="1.4" /><path d="M6 1a5 5 0 0 1 0 10Z" fill="currentColor" /></svg>
      );
    case "review": // ring with dot (an eye)
      return (
        <svg {...common}><circle cx="6" cy="6" r="5" fill="none" stroke="currentColor" strokeWidth="1.4" strokeDasharray="2.2 1.4" /><circle cx="6" cy="6" r="2" fill="currentColor" /></svg>
      );
    case "fraud": // triangle with bang
      return (
        <svg {...common}><path d="M6 0.8 11.4 10.8H0.6Z" fill="currentColor" /><path d="M6 4.3v3.2" stroke="var(--fm-ink)" strokeWidth="1.4" strokeLinecap="round" /><circle cx="6" cy="9.1" r="0.8" fill="var(--fm-ink)" /></svg>
      );
    case "live":
      return <svg {...common}><circle cx="6" cy="6" r="3.2" fill="currentColor" className="fm-live-dot" /></svg>;
    default:
      return <svg {...common}><circle cx="6" cy="6" r="3" fill="none" stroke="currentColor" strokeWidth="1.4" /></svg>;
  }
}
