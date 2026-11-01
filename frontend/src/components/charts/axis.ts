import { chartTheme } from "../../tokens/tokens";

/** Mono 10.5px tick style, no axis line, no tick marks. */
export function axisProps() {
  const t = chartTheme();
  return {
    tick: { fill: t.tick, fontSize: 10.5, fontFamily: "var(--fm-font-mono)" },
    axisLine: false as const,
    tickLine: false as const,
  };
}
