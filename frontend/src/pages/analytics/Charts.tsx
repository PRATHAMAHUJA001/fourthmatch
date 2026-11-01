import { useEffect, useState } from "react";
import { Bar, BarChart, LabelList, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { axisProps } from "../../components/charts/axis";
import { CategoryTick } from "../../components/charts/CategoryTick";
import { ChartTooltip } from "../../components/charts/ChartTooltip";
import { formatDate, formatINRCompact } from "../../lib/format";
import { useTheme } from "../../lib/theme";
import { chartTheme } from "../../tokens/tokens";
import type { AnalyticsRead } from "../../types/api";
import { truncate, typeLabel } from "./labels";

/** True below 640px: category labels get a narrower gutter so bars keep their length. */
function useNarrow() {
  const q = "(max-width: 640px)";
  const [n, setN] = useState(() => typeof window !== "undefined" && !!window.matchMedia?.(q).matches);
  useEffect(() => {
    const mq = window.matchMedia?.(q);
    if (!mq) return;
    const on = () => setN(mq.matches);
    mq.addEventListener?.("change", on);
    return () => mq.removeEventListener?.("change", on);
  }, []);
  return n;
}

/** Value label at the end of a bar, in the quiet tone. Drawn by hand so Recharts never wraps it. */
function endLabel(fill: string, fmt: (v: number) => string) {
  return {
    content: (p: { x?: number | string; y?: number | string; width?: number | string; height?: number | string; value?: unknown }) => (
      <text x={Number(p.x) + Number(p.width) + 10} y={Number(p.y) + Number(p.height) / 2} dy={4} fill={fill} fontSize={12} fontFamily="var(--fm-font-mono)">
        {fmt(Number(p.value))}
      </text>
    ),
  };
}

export function HeldByVendorChart({ data }: { data: AnalyticsRead["held_by_vendor"] }) {
  const { theme } = useTheme();
  const c = chartTheme();
  const narrow = useNarrow();
  const rows = data.map((d) => ({ ...d, short: truncate(d.vendor_name, narrow ? 14 : 24) }));
  return (
    <div style={{ height: Math.max(200, rows.length * 44) }} role="img" aria-label="Rupees held by vendor, bar chart">
      <ResponsiveContainer key={theme} width="100%" height="100%">
        <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 72, bottom: 0, left: 0 }} barCategoryGap={14}>
          <XAxis type="number" hide />
          <YAxis type="category" dataKey="short" width={narrow ? 112 : 190} {...axisProps()} tick={<CategoryTick />} />
          <Tooltip cursor={{ fill: c.cursor, opacity: 0.6, radius: 8 }} content={<ChartTooltip kind="money" names={{ held_paise: "Held" }} title={(_, p) => (p[0]?.payload as { vendor_name: string } | undefined)?.vendor_name} />} />
          <Bar dataKey="held_paise" fill={c.hold} radius={[0, 6, 6, 0]} barSize={14} isAnimationActive={false}>
            <LabelList dataKey="held_paise" {...endLabel(c.tick, formatINRCompact)} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function TrendChart({ data }: { data: AnalyticsRead["trend"] }) {
  const { theme } = useTheme();
  const c = chartTheme();
  const ax = axisProps();
  return (
    <div className="h-[280px]" role="img" aria-label="Deliveries and discrepancies per day over 30 days">
      <ResponsiveContainer key={theme} width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <XAxis dataKey="date" {...ax} tickFormatter={formatDate} interval="preserveStartEnd" minTickGap={48} tickMargin={10} />
          <YAxis {...ax} width={28} allowDecimals={false} tickCount={4} />
          <Tooltip cursor={{ stroke: c.faint, strokeWidth: 1 }} content={<ChartTooltip names={{ deliveries: "Deliveries", discrepancies: "Discrepancies" }} title={(l) => formatDate(String(l))} />} />
          <Line type="monotone" dataKey="deliveries" stroke={c.accent} strokeWidth={2} dot={false} activeDot={{ r: 4, strokeWidth: 0 }} isAnimationActive={false} />
          <Line type="monotone" dataKey="discrepancies" stroke={c.hold} strokeWidth={2} dot={false} activeDot={{ r: 4, strokeWidth: 0 }} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function TypeMixChart({ data }: { data: AnalyticsRead["type_mix"] }) {
  const { theme } = useTheme();
  const c = chartTheme();
  const narrow = useNarrow();
  const rows = data.map((d) => ({ ...d, label: narrow ? truncate(typeLabel(d.type), 16) : typeLabel(d.type) }));
  return (
    <div style={{ height: Math.max(200, rows.length * 44) }} role="img" aria-label="Discrepancy type mix, bar chart">
      <ResponsiveContainer key={theme} width="100%" height="100%">
        <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 48, bottom: 0, left: 0 }} barCategoryGap={14}>
          <XAxis type="number" hide allowDecimals={false} />
          <YAxis type="category" dataKey="label" width={narrow ? 120 : 200} {...axisProps()} tick={<CategoryTick />} />
          <Tooltip cursor={{ fill: c.cursor, opacity: 0.6, radius: 8 }} content={<ChartTooltip names={{ count: "Cases" }} />} />
          <Bar dataKey="count" fill={c.accent} radius={[0, 6, 6, 0]} barSize={14} isAnimationActive={false}>
            <LabelList dataKey="count" {...endLabel(c.tick, (v) => String(v))} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
