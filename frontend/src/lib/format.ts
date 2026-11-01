/** Money is integer paise everywhere (backend contract). Format in en-IN. */

export function formatINR(paise: number, opts?: { sign?: boolean }): string {
  const negative = paise < 0;
  const rupees = Math.abs(paise) / 100;
  const formatted = new Intl.NumberFormat("en-IN", {
    maximumFractionDigits: Number.isInteger(rupees) ? 0 : 2,
    minimumFractionDigits: Number.isInteger(rupees) ? 0 : 2,
  }).format(rupees);
  const prefix = negative ? "−₹" : opts?.sign && paise > 0 ? "+₹" : "₹";
  return `${prefix}${formatted}`;
}

/** Compact Indian units: ₹12.2 L, ₹4.9 Cr. For chart axes only; tables use formatINR. */
export function formatINRCompact(paise: number): string {
  const r = Math.abs(paise) / 100;
  const sign = paise < 0 ? "−" : "";
  if (r >= 1e7) return `${sign}₹${(r / 1e7).toFixed(r >= 1e8 ? 0 : 1)} Cr`;
  if (r >= 1e5) return `${sign}₹${(r / 1e5).toFixed(r >= 1e6 ? 0 : 1)} L`;
  if (r >= 1e3) return `${sign}₹${(r / 1e3).toFixed(r >= 1e4 ? 0 : 1)} K`;
  return `${sign}₹${Math.round(r)}`;
}

export function formatQty(value: number, unit?: string): string {
  const n = new Intl.NumberFormat("en-IN").format(value);
  return unit ? `${n} ${unit}` : n;
}

export function formatPct(value: number, digits = 1): string {
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  return `${sign}${Math.abs(value).toFixed(digits)}%`;
}

export function formatTs(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const date = d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric", timeZone: "Asia/Kolkata" });
  const time = d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Asia/Kolkata" });
  return `${date} · ${time}`;
}

export function formatDate(iso: string): string {
  const d = new Date(iso.length === 10 ? `${iso}T00:00:00Z` : iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", timeZone: "UTC" });
}

export function formatVariance(observed: number, expected: number): { text: string; pct: number } {
  if (expected === 0) return { text: "—", pct: 0 };
  const pct = ((observed - expected) / expected) * 100;
  const diff = observed - expected;
  const sign = diff > 0 ? "+" : diff < 0 ? "−" : "";
  return { text: `${sign}${Math.abs(diff)} (${formatPct(pct)})`, pct };
}

export function shortHash(h: string, n = 8): string {
  return h.length > n * 2 ? `${h.slice(0, n)}…${h.slice(-4)}` : h;
}

export function titleCase(s: string): string {
  return s.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
