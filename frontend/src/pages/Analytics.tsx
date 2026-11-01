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
    <span className="inline-flex items-center justify-end gap-2" role="meter" aria-valuenow={score} aria-valuemin={0} aria-valuemax={max} aria-label={`Risk score ${score}`}>
      <span className="relative h-[3px] w-14 bg-fm-border" aria-hidden>
        <span className="absolute inset-y-0 left-0 bg-fm-hold" style={{ width: `${pct}%` }} />
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
      { id: "rank", header: "#", enableSorting: false, meta: { width: "44px" }, cell: ({ row }) => <span className="font-mono text-fm-faint">{String(row.index + 1).padStart(2, "0")}</span> },
      { accessorKey: "vendor_name", header: "Vendor", cell: (i) => <span className="font-medium">{i.getValue<string>()}</span> },
      { accessorKey: "cases", header: "Cases", meta: { align: "right" }, cell: (i) => <span className="font-mono tabular-nums">{i.getValue<number>()}</span> },
      { accessorKey: "discrepancies", header: "Discrepancies", meta: { align: "right" }, cell: (i) => <span className="font-mono tabular-nums">{i.getValue<number>()}</span> },
      { accessorKey: "held_paise", header: "Held", meta: { align: "right" }, cell: (i) => <Money paise={i.getValue<number>()} /> },
      { accessorKey: "risk_score", header: "Risk score", meta: { align: "right" }, cell: (i) => <RiskMeter score={i.getValue<number>()} max={max} /> },
    ];
  }, [q.data]);

  const header = <PageHeader eyebrow="Analytics · last 30 days" title="Where the money is held" />;

  if (q.isError) return <div>{header}<Panel><ErrorState message={q.error.message} action={null} /></Panel></div>;
  if (!q.data) {
    return (
      <div>
        {header}
        <Skeleton className="mb-4 h-[88px] w-full" />
        <div className="grid gap-3 lg:grid-cols-2"><Skeleton className="h-[320px]" /><Skeleton className="h-[320px]" /></div>
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
    <div className="fm-rise">
      {header}
      <KpiStrip className="mb-3 md:grid-cols-4">
        <KpiTile label="Total held" tone="hold" value={formatINR(totalHeld)} hint={`${d.held_by_vendor.length} vendors`} />
        <KpiTile label="Deliveries · 30 d" value={deliveries} hint={`${discrepancies} with a discrepancy`} spark={d.trend.map((t) => t.deliveries)} />
        <KpiTile label="Discrepancy rate" value={rate.toFixed(1)} unit="%" hint="discrepancies / deliveries" spark={d.trend.map((t) => t.discrepancies)} />
        <KpiTile label="Highest-risk vendor" value={<span className="block truncate font-sans text-[18px] font-semibold tracking-normal">{top?.vendor_name ?? "—"}</span>} hint={top ? `risk score ${top.risk_score}` : undefined} />
      </KpiStrip>

      <div className="grid gap-3 lg:grid-cols-2">
        <Panel index="01" title="Rupees held by vendor" subtitle="from computed decisions"><HeldByVendorChart data={d.held_by_vendor} /></Panel>
        <Panel
          index="02" title="Discrepancy trend"
          actions={
            <span className="flex items-center gap-3 font-mono text-[10.5px] text-fm-muted">
              <span className="flex items-center gap-1.5"><span className="h-[2px] w-3 bg-fm-review" />deliveries</span>
              <span className="flex items-center gap-1.5"><span className="h-[2px] w-3 bg-fm-hold" />discrepancies</span>
            </span>
          }
        >
          <TrendChart data={d.trend} />
        </Panel>
        <Panel index="03" title="Discrepancy type mix"><TypeMixChart data={d.type_mix} /></Panel>
        <Panel index="04" title="Vendor risk leaderboard" padded={false}>
          <DataTable<Risk> columns={columns} data={d.vendor_risk} label="Vendor risk leaderboard" />
        </Panel>
      </div>

      <p className="mt-3 text-[11.5px] text-fm-faint">30-day history is synthetic presentation data. Per-case figures come from computed decisions.</p>
    </div>
  );
}
