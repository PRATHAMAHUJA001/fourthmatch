import type { ReactNode } from "react";
import { formatINR } from "../../lib/format";

interface Entry { name?: string | number; value?: number | string; color?: string; dataKey?: string | number; payload?: unknown }

interface Props {
  active?: boolean;
  payload?: Entry[];
  label?: string | number;
  /** Heading override; defaults to the axis label. */
  title?: (label: string | number | undefined, payload: Entry[]) => ReactNode;
  /** "money" values are paise and render through formatINR. */
  kind?: "money" | "count";
  names?: Record<string, string>;
}

/** Flat tooltip panel shared by every chart: raised surface, strong hairline, mono values. */
export function ChartTooltip({ active, payload, label, title, kind = "count", names }: Props) {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <div className="min-w-[132px] rounded-fm-sm border border-fm-border-strong bg-fm-raised px-2.5 py-2 text-[11.5px]">
      <div className="fm-label mb-1.5 !text-fm-text">{title ? title(label, payload) : label}</div>
      <ul className="flex flex-col gap-1">
        {payload.map((p) => {
          const key = String(p.dataKey ?? p.name);
          const v = typeof p.value === "number" ? p.value : Number(p.value);
          return (
            <li key={key} className="flex items-center justify-between gap-4">
              <span className="flex items-center gap-1.5 text-fm-muted">
                <span className="h-[2px] w-2.5" style={{ background: p.color }} aria-hidden />
                {names?.[key] ?? p.name}
              </span>
              <span className="font-mono tabular-nums text-fm-text">{kind === "money" ? formatINR(v) : v}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
