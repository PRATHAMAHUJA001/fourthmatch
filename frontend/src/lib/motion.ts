/** Hand-rolled motion primitives (no animation library). Everything is a no-op under
 *  prefers-reduced-motion: content renders in its final state. */
import { useEffect, useRef, useState, type RefObject } from "react";

export function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function useReducedMotion(): boolean {
  const [reduce, setReduce] = useState(prefersReducedMotion);
  useEffect(() => {
    if (!window.matchMedia) return;
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const on = () => setReduce(mq.matches);
    mq.addEventListener?.("change", on);
    return () => mq.removeEventListener?.("change", on);
  }, []);
  return reduce;
}

export const clamp01 = (x: number) => (x < 0 ? 0 : x > 1 ? 1 : x);
/** Maps x in [a, b] to [0, 1], clamped. */
export const range = (x: number, a: number, b: number) => clamp01((x - a) / (b - a));
export const easeOut = (t: number) => 1 - Math.pow(1 - t, 3);

/** Adds `is-in` to the element once it enters the viewport (pair with the .fm-reveal class). */
export function useReveal<T extends HTMLElement>(threshold = 0.15): RefObject<T> {
  const ref = useRef<T>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (prefersReducedMotion() || typeof IntersectionObserver === "undefined") { el.classList.add("is-in"); return; }
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) if (e.isIntersecting) { e.target.classList.add("is-in"); io.unobserve(e.target); }
    }, { threshold, rootMargin: "0px 0px -8% 0px" });
    io.observe(el);
    return () => io.disconnect();
  }, [threshold]);
  return ref;
}

/** Progress (0..1) of the window scrolling through a tall element: 0 when its top reaches the
 *  viewport top, 1 when its bottom reaches the viewport bottom. Updated once per animation frame,
 *  only while the element is near the viewport. */
export function useScrollProgress<T extends HTMLElement>(ref: RefObject<T>, enabled = true): number {
  const [p, setP] = useState(0);
  useEffect(() => {
    if (!enabled) return;
    let raf = 0;
    let last = -1;
    const measure = () => {
      raf = 0;
      const el = ref.current;
      if (!el) return;
      const r = el.getBoundingClientRect();
      const vh = window.innerHeight;
      if (r.bottom < -vh || r.top > 2 * vh) return;
      const total = r.height - vh;
      const next = total > 0 ? clamp01(-r.top / total) : r.top <= 0 ? 1 : 0;
      if (Math.abs(next - last) > 0.0008) { last = next; setP(next); }
    };
    const on = () => { if (!raf) raf = requestAnimationFrame(measure); };
    measure();
    window.addEventListener("scroll", on, { passive: true });
    window.addEventListener("resize", on);
    return () => { window.removeEventListener("scroll", on); window.removeEventListener("resize", on); cancelAnimationFrame(raf); };
  }, [ref, enabled]);
  return p;
}

/** Calls `fn(scrollY)` once per frame while scrolling. For direct style writes (parallax). */
export function useScrollFrame(fn: (y: number) => void, enabled = true) {
  const fnRef = useRef(fn);
  fnRef.current = fn;
  useEffect(() => {
    if (!enabled) return;
    let raf = 0;
    const tick = () => { raf = 0; fnRef.current(window.scrollY); };
    const on = () => { if (!raf) raf = requestAnimationFrame(tick); };
    tick();
    window.addEventListener("scroll", on, { passive: true });
    window.addEventListener("resize", on);
    return () => { window.removeEventListener("scroll", on); window.removeEventListener("resize", on); cancelAnimationFrame(raf); };
  }, [enabled]);
}
