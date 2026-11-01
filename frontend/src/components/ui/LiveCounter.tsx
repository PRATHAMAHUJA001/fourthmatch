import { cn } from "../../lib/cn";

/** Live object count. Every value shown is a real integer from the pipeline (one step per
 *  confirmed SAM track); a new value slides up into place. Nothing is interpolated, so the
 *  counter never displays a number that was not observed. */
export function LiveCounter({ value, className, label }: { value: number; className?: string; label?: string }) {
  const v = Math.max(0, value);
  return (
    <span className={cn("fm-figure inline-flex overflow-hidden leading-none", className)} aria-label={label ? `${label}: ${v}` : String(v)} role="status">
      <span key={v} className="fm-tick inline-block" aria-hidden>{v}</span>
    </span>
  );
}
