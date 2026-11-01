import { useEffect, useRef, useState } from "react";
import { cn } from "../../lib/cn";

/** Odometer-style mono counter. Each digit rolls; respects reduced motion via CSS. */
export function LiveCounter({ value, digits = 2, className, label }: { value: number; digits?: number; className?: string; label?: string }) {
  const str = String(Math.max(0, value)).padStart(digits, "0");
  return (
    <span className={cn("inline-flex font-mono tabular-nums leading-none", className)} aria-label={label ? `${label}: ${value}` : String(value)} role="status">
      {str.split("").map((d, i) => (
        <span key={i} className="relative inline-block h-[1em] w-[0.62em] overflow-hidden" aria-hidden>
          <span
            className="absolute left-0 top-0 flex flex-col transition-transform duration-300 ease-[var(--fm-ease)]"
            style={{ transform: `translateY(-${Number(d) * 10}%)` }}
          >
            {Array.from({ length: 10 }, (_, n) => <span key={n} className="block h-[1em] leading-[1em]">{n}</span>)}
          </span>
        </span>
      ))}
    </span>
  );
}

/** Counts from 0 to `to` once when `run` flips true. Used for the hero reveal. */
export function useCountUp(to: number, run: boolean, ms = 1400) {
  const [v, setV] = useState(run ? 0 : to);
  const raf = useRef(0);
  useEffect(() => {
    if (!run) { setV(to); return; }
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduce) { setV(to); return; }
    const start = performance.now();
    const tick = (t: number) => {
      const p = Math.min(1, (t - start) / ms);
      setV(Math.round(to * (1 - Math.pow(1 - p, 3))));
      if (p < 1) raf.current = requestAnimationFrame(tick);
    };
    setV(0);
    raf.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf.current);
  }, [to, run, ms]);
  return v;
}
