import { useQuery } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { useMemo } from "react";
import { Panel, PageHeader } from "../components/ui/Panel";
import { KpiStrip, KpiTile } from "../components/ui/KpiTile";
import { DataTable } from "../components/ui/DataTable";
import { ErrorState, Skeleton } from "../components/ui/EmptyState";
import { Money } from "../components/ui/Money";
import { api } from "../lib/api";
import { formatINR } from "../lib/format";
import type { AnalyticsRead } from "../types/api";
import { HeldByVendorChart, TrendChart, TypeMixChart } from "./analytics/Charts";

type Risk = AnalyticsRead["vendor_risk"][number];

function RiskMeter({ score, max }: { score: number; max: number }) {
  const pct = max > 0 ? Math.max(0, Math.min(100, (score / max) * 100)) : 0;
  return (
    <span className="inline-flex items-center justify-end gap-3" role="meter" aria-valuenow={score} aria-valuemin={0} aria-valuemax={max} aria-label={`Risk score ${score}`}>
      <span className="relative h-1.5 w-12 overflow-hidden rounded-full bg-fm-hover" aria-hidden>
        <span className="absolute inset-y-0 left-0 rounded-full bg-fm-hold-fill" style={{ width: `${pct}%` }} />
      </span>
      <span className="w-7 text-right font-mono tabular-nums">{score}</span>
    </span>
  );
}

export function Analytics() {
  const q = useQuery({ queryKey: ["analytics"], queryFn: api.analytics });

  const columns = useMemo<ColumnDef<Risk, unknown>[]>(() => {
    const max = Math.max(100, ...(q.data?.vendor_risk.map((r) => r.risk_score) ?? [0]));
    return [
      { id: "rank", header: "#", enableSorting: false, meta: { width: "44px" }, cell: ({ row }) => <span className="tabular-nums text-fm-faint">{row.index + 1}</span> },
      { accessorKey: "vendor_name", header: "Vendor", cell: (i) => <span className="font-medium">{i.getValue<string>()}</span> },
      { accessorKey: "cases", header: "Cases", meta: { align: "right" }, cell: (i) => <span className="font-mono tabular-nums">{i.getValue<number>()}</span> },
      { accessorKey: "discrepancies", header: "Issues", meta: { align: "right" }, cell: (i) => <span className="font-mono tabular-nums">{i.getValue<number>()}</span> },
      { accessorKey: "held_paise", header: "Held", meta: { align: "right" }, cell: (i) => <Money paise={i.getValue<number>()} /> },
      { accessorKey: "risk_score", header: "Risk", meta: { align: "right" }, cell: (i) => <RiskMeter score={i.getValue<number>()} max={max} /> },
    ];
  }, [q.data]);

  const header = <PageHeader eyebrow="Trends · last 30 days" title="Where the money is held." meta={<span>Rupees withheld by vendor, how often deliveries disagree with paper, and why.</span>} />;

  if (q.isError) return <div>{header}<Panel><ErrorState message={q.error.message} action={null} /></Panel></div>;
  if (!q.data) {
    return (
      <div>
        {header}
        <Skeleton className="mb-6 h-[148px] w-full rounded-fm" />
        <div className="grid gap-6 lg:grid-cols-2"><Skeleton className="h-[340px] rounded-fm" /><Skeleton className="h-[340px] rounded-fm" /></div>
      </div>
    );
  }

  const d = q.data;
  const totalHeld = d.held_by_vendor.reduce((s, v) => s + v.held_paise, 0);
  const deliveries = d.trend.reduce((s, t) => s + t.deliveries, 0);
  const discrepancies = d.trend.reduce((s, t) => s + t.discrepancies, 0);
  const rate = deliveries > 0 ? (discrepancies / deliveries) * 100 : 0;
  const top = [...d.vendor_risk].sort((a, b) => b.risk_score - a.risk_score || b.held_paise - a.held_paise)[0];

  return (
    <div>
      {header}
      <KpiStrip className="mb-6 grid-cols-2 md:grid-cols-4 max-md:divide-x [&>*:nth-child(3)]:max-md:border-l-0">
        <KpiTile label="Total held" tone="hold" value={formatINR(totalHeld)} hint={`Across ${d.held_by_vendor.length} vendors`} />
        <KpiTile label="Deliveries" value={deliveries} hint={`${discrepancies} with a discrepancy`} spark={d.trend.map((t) => t.deliveries)} />
        <KpiTile label="Discrepancy rate" value={rate.toFixed(1)} unit="%" hint="Discrepancies per delivery" spark={d.trend.map((t) => t.discrepancies)} />
        <KpiTile label="Highest-risk vendor" value={<span className="block truncate text-[24px] font-semibold tracking-[-0.022em] max-sm:text-[19px]">{top?.vendor_name ?? "—"}</span>} hint={top ? `Risk score ${top.risk_score}` : undefined} />
      </KpiStrip>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Rupees held by vendor" subtitle="From computed decisions"><HeldByVendorChart data={d.held_by_vendor} /></Panel>
        <Panel
          title="Discrepancy trend"
          subtitle="Per day, last 30 days"
          actions={
            <span className="flex items-center gap-4 text-[12px] text-fm-muted">
              <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-fm-accent" />Deliveries</span>
              <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-fm-hold-fill" />Discrepancies</span>
            </span>
          }
        >
          <TrendChart data={d.trend} />
        </Panel>
        <Panel title="Why payments were held" subtitle="Discrepancy type, by case"><TypeMixChart data={d.type_mix} /></Panel>
        <Panel title="Vendor risk" subtitle="Ranked by risk score" padded={false} bodyClassName="px-2 pb-2">
          <DataTable<Risk> columns={columns} data={d.vendor_risk} label="Vendor risk leaderboard" />
        </Panel>
      </div>

      <p className="mt-6 text-[13px] text-fm-faint">30-day history is synthetic presentation data. Per-case figures come from computed decisions.</p>
    </div>
  );
}
