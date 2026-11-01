/** Money is integer paise everywhere (backend contract). Format in en-IN. */

export function formatINR(paise: number, opts?: { sign?: boolean }): string {
  const negative = paise < 0;
  const rupees = Math.abs(paise) / 100;
  const formatted = new Intl.NumberFormat("en-IN", {
    maximumFractionDigits: Number.isInteger(rupees) ? 0 : 2,
    minimumFractionDigits: Number.isInteger(rupees) ? 0 : 2,
  }).format(rupees);
  const prefix = negative ? "−₹" : opts?.sign ? "+₹" : "₹";
  return `${prefix}${formatted}`;
}

export function formatQty(value: number, unit?: string): string {
  const n = new Intl.NumberFormat("en-IN").format(value);
  return unit ? `${n} ${unit}` : n;
}

export function formatPct(value: number, digits = 1): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(digits)}%`;
}

export function formatTs(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const date = d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
  const time = d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false });
  return `${date} · ${time}`;
}

export function formatVariance(observed: number, expected: number): { text: string; pct: number } {
  if (expected === 0) return { text: "—", pct: 0 };
  const pct = ((observed - expected) / expected) * 100;
  const diff = observed - expected;
  const sign = diff > 0 ? "+" : "";
  return { text: `${sign}${diff} (${formatPct(pct)})`, pct };
}
