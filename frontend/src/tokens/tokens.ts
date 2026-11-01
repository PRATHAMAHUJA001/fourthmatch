/** TS mirror of CSS tokens for JS consumers (Recharts, canvas). Read live values. */
export function cssVar(name: string): string {
  if (typeof document === "undefined") return "";
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

export const chartColors = {
  hold: () => cssVar("--fm-hold") || "#F5A524",
  verified: () => cssVar("--fm-verified") || "#2BB673",
  fraud: () => cssVar("--fm-fraud") || "#E5484D",
  review: () => cssVar("--fm-review") || "#6B7A90",
  grid: () => cssVar("--fm-border") || "#252B33",
  text: () => cssVar("--fm-muted") || "#8A93A0",
};

/** Shared Recharts styling, resolved at render so light/dark both work. */
export function chartTheme() {
  return {
    grid: cssVar("--fm-border") || "#22262c",
    tick: cssVar("--fm-muted") || "#8b9098",
    text: cssVar("--fm-text") || "#ecedee",
    hold: cssVar("--fm-hold") || "#ffb224",
    verified: cssVar("--fm-verified") || "#3dd68c",
    review: cssVar("--fm-review") || "#8fa1bb",
    faint: cssVar("--fm-faint") || "#5d636c",
    cursor: cssVar("--fm-hover") || "#1d2025",
  };
}
