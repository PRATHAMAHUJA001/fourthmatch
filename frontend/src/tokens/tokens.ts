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
