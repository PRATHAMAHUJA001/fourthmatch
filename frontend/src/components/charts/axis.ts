import { chartTheme } from "../../tokens/tokens";

/** Quiet axis: 11px Inter ticks in the faint tone, no axis line, no tick marks. */
export function axisProps() {
  const t = chartTheme();
  return {
    tick: { fill: t.faint, fontSize: 11, fontFamily: "var(--fm-font-sans)" },
    axisLine: false as const,
    tickLine: false as const,
  };
}
