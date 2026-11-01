/** TS mirror of CSS tokens for JS consumers (Recharts, canvas). Read live values. */
export function cssVar(name: string): string {
  if (typeof document === "undefined") return "";
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}


/** Shared Recharts styling, resolved at render so light/dark both work. */
export function chartTheme() {
  return {
    grid: cssVar("--fm-border") || "rgba(0,0,0,.08)",
    tick: cssVar("--fm-muted") || "#6e6e73",
    text: cssVar("--fm-text") || "#1d1d1f",
    hold: cssVar("--fm-hold-fill") || "#ff9f0a",
    verified: cssVar("--fm-verified-fill") || "#30d158",
    review: cssVar("--fm-review-fill") || "#8e8e93",
    accent: cssVar("--fm-accent") || "#0071e3",
    faint: cssVar("--fm-faint") || "#86868b",
    cursor: cssVar("--fm-hover") || "#ebebef",
  };
}
