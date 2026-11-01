import { Bar, BarChart, CartesianGrid, Line, LineChart, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { axisProps } from "../../components/charts/axis";
import { CategoryTick } from "../../components/charts/CategoryTick";
import { ChartTooltip } from "../../components/charts/ChartTooltip";
import { formatDate, formatINRCompact } from "../../lib/format";
import { useTheme } from "../../lib/theme";
import { chartTheme } from "../../tokens/tokens";
import type { AnalyticsRead } from "../../types/api";
import { truncate, typeLabel } from "./labels";

const MARGIN = { top: 4, right: 28, bottom: 0, left: 0 };

export function HeldByVendorChart({ data }: { data: AnalyticsRead["held_by_vendor"] }) {
  const { theme } = useTheme();
  const c = chartTheme();
  const ax = axisProps();
  const rows = data.map((d) => ({ ...d, short: truncate(d.vendor_name, 22) }));
  return (
    <div className="h-[260px]" role="img" aria-label="Rupees held by vendor, bar chart">
      <ResponsiveContainer key={theme} width="100%" height="100%">
        <BarChart data={rows} layout="vertical" margin={MARGIN} barCategoryGap={6}>
          <CartesianGrid horizontal={false} stroke={c.grid} strokeDasharray="2 4" />
          <XAxis type="number" {...ax} tickFormatter={formatINRCompact} />
          <YAxis type="category" dataKey="short" width={150} {...ax} tick={<CategoryTick />} />
          <Tooltip cursor={{ fill: c.cursor, opacity: 0.5 }} content={<ChartTooltip kind="money" names={{ held_paise: "Held" }} title={(_, p) => (p[0]?.payload as { vendor_name: string } | undefined)?.vendor_name} />} />
          <Bar dataKey="held_paise" fill={c.hold} radius={1} barSize={10} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function TrendChart({ data }: { data: AnalyticsRead["trend"] }) {
  const { theme } = useTheme();
  const c = chartTheme();
  const ax = axisProps();
  const last7 = data.length > 7 ? data[data.length - 7].date : data[0]?.date;
  const end = data[data.length - 1]?.date;
  return (
    <div className="h-[260px]" role="img" aria-label="Deliveries and discrepancies per day over 30 days">
      <ResponsiveContainer key={theme} width="100%" height="100%">
        <LineChart data={data} margin={MARGIN}>
          <CartesianGrid vertical={false} stroke={c.grid} strokeDasharray="2 4" />
          {last7 && end && <ReferenceArea x1={last7} x2={end} fill={c.grid} fillOpacity={0.55} ifOverflow="visible" />}
          <XAxis dataKey="date" {...ax} tickFormatter={formatDate} interval={4} />
          <YAxis {...ax} width={28} allowDecimals={false} />
          {last7 && <ReferenceLine x={last7} stroke={c.faint} strokeDasharray="2 4" label={{ value: "last 7 d", position: "insideTopLeft", fill: c.tick, fontSize: 10, fontFamily: "var(--fm-font-mono)" }} />}
          <Tooltip cursor={{ stroke: c.faint, strokeDasharray: "2 4" }} content={<ChartTooltip names={{ deliveries: "Deliveries", discrepancies: "Discrepancies" }} title={(l) => formatDate(String(l))} />} />
          <Line type="linear" dataKey="deliveries" stroke={c.review} strokeWidth={1.25} dot={false} activeDot={{ r: 3 }} isAnimationActive={false} />
          <Line type="linear" dataKey="discrepancies" stroke={c.hold} strokeWidth={1.5} dot={{ r: 1.75, fill: c.hold, strokeWidth: 0 }} activeDot={{ r: 3.5 }} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function TypeMixChart({ data }: { data: AnalyticsRead["type_mix"] }) {
  const { theme } = useTheme();
  const c = chartTheme();
  const ax = axisProps();
  const rows = data.map((d) => ({ ...d, label: typeLabel(d.type) }));
  return (
    <div className="h-[260px]" role="img" aria-label="Discrepancy type mix, bar chart">
      <ResponsiveContainer key={theme} width="100%" height="100%">
        <BarChart data={rows} layout="vertical" margin={MARGIN} barCategoryGap={6}>
          <CartesianGrid horizontal={false} stroke={c.grid} strokeDasharray="2 4" />
          <XAxis type="number" {...ax} allowDecimals={false} />
          <YAxis type="category" dataKey="label" width={176} {...ax} tick={<CategoryTick />} />
          <Tooltip cursor={{ fill: c.cursor, opacity: 0.5 }} content={<ChartTooltip names={{ count: "Cases" }} />} />
          <Bar dataKey="count" fill={c.review} radius={1} barSize={10} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
