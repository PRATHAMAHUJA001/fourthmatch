import type { ColumnDef } from "@tanstack/react-table";
import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Button } from "../components/ui/Button";
import { DataTable } from "../components/ui/DataTable";
import { EmptyState, Skeleton, SkeletonRows } from "../components/ui/EmptyState";
import { KpiTile } from "../components/ui/KpiTile";
import { Money, Qty } from "../components/ui/Money";
import { Panel } from "../components/ui/Panel";
import { StatusBadge } from "../components/ui/StatusBadge";
import { Stepper } from "../components/ui/Stepper";
import { formatINR } from "../lib/format";
import { useTheme } from "../lib/theme";
import { chartColors } from "../tokens/tokens";
import type { JobStatus, Verdict } from "../types/api";

interface DemoRow {
  po: string; vendor: string; ordered: number; observed: number; amount: number; verdict: Verdict;
}
const DEMO: DemoRow[] = [
  { po: "FM/PO/26-27/001", vendor: "Shree Ganesh Packaging", ordered: 12, observed: 12, amount: 778800, verdict: "approve" },
  { po: "FM/PO/26-27/002", vendor: "Shree Ganesh Packaging", ordered: 12, observed: 10, amount: 778800, verdict: "partial_pay" },
  { po: "FM/PO/26-27/005", vendor: "Bharat Steel Rolling", ordered: 8, observed: 8, amount: 36249600, verdict: "hold" },
  { po: "FM/PO/26-27/007", vendor: "Shree Ganesh Packaging", ordered: 120, observed: 120, amount: 9251200, verdict: "human_review" },
];

const CHART = [
  { day: "Mon", holds: 4, verified: 18 },
  { day: "Tue", holds: 6, verified: 22 },
  { day: "Wed", holds: 3, verified: 25 },
  { day: "Thu", holds: 7, verified: 19 },
  { day: "Fri", holds: 5, verified: 21 },
];

function Swatch({ name, varName, textOn = "text-fm-text" }: { name: string; varName: string; textOn?: string }) {
  return (
    <div className="overflow-hidden rounded-fm border border-fm-border">
      <div className="h-12" style={{ background: `var(${varName})` }} />
      <div className="bg-fm-panel px-2 py-1.5">
        <div className={`text-[11px] font-medium ${textOn}`}>{name}</div>
        <div className="font-mono text-[10px] text-fm-muted">{varName}</div>
      </div>
    </div>
  );
}

export function Styleguide() {
  const { theme, toggle } = useTheme();
  const [step, setStep] = useState<JobStatus>("tracking");
  const [showSkeleton, setShowSkeleton] = useState(false);

  const columns = useMemo<ColumnDef<DemoRow, unknown>[]>(() => [
    { accessorKey: "po", header: "PO", cell: ({ getValue }) => <span className="font-mono text-[11px]">{String(getValue())}</span> },
    { accessorKey: "vendor", header: "Vendor" },
    { accessorKey: "ordered", header: "Ordered", cell: ({ getValue }) => <Qty value={Number(getValue())} /> },
    { accessorKey: "observed", header: "Observed (SAM)", cell: ({ getValue }) => <Qty value={Number(getValue())} /> },
    { accessorKey: "amount", header: "Invoice", cell: ({ getValue }) => <Money paise={Number(getValue())} /> },
    { accessorKey: "verdict", header: "Verdict", cell: ({ getValue }) => <StatusBadge verdict={getValue() as Verdict} /> },
  ], []);

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[20px] font-semibold tracking-tight">Design system</h1>
          <p className="mt-0.5 max-w-xl text-[12px] text-fm-muted">
            Industrial control room. Graphite, hairlines, IBM Plex — signal colour always paired with icon + label.
            Theme: <span className="font-mono">{theme}</span>
          </p>
        </div>
        <Button onClick={toggle} aria-label="Toggle theme">Toggle {theme === "dark" ? "light" : "dark"}</Button>
      </div>

      <Panel title="Colour tokens" subtitle="CSS variables — components never hardcode hex">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-6">
          <Swatch name="Background" varName="--fm-bg" />
          <Swatch name="Panel" varName="--fm-panel" />
          <Swatch name="Raised" varName="--fm-raised" />
          <Swatch name="Border" varName="--fm-border" />
          <Swatch name="Hold · amber" varName="--fm-hold" />
          <Swatch name="Verified · green" varName="--fm-verified" />
          <Swatch name="Fraud · red" varName="--fm-fraud" />
          <Swatch name="Review · slate" varName="--fm-review" />
        </div>
        <p className="mt-3 text-[11px] text-fm-muted">
          Radius max 6px · borders 1px · no gradients, glass, emoji, or purple. Motion 150ms, respects reduced-motion.
        </p>
      </Panel>

      <Panel title="Typography" subtitle="IBM Plex Sans for UI · IBM Plex Mono for every quantity, ID, amount, timestamp">
        <div className="flex flex-col gap-2">
          <p className="text-[20px] font-semibold tracking-tight">Dock decision needs reading fast — 20px semibold</p>
          <p className="text-[13px]">Body 13px. The GRN says 12 cartons; SAM tracked 10 distinct objects across 214 frames.</p>
          <p className="font-mono text-[13px] tabular-nums">FM/PO/26-27/002 · {formatINR(124500000)} · 2026-11-01 14:32 · track_0042</p>
          <p className="font-mono text-[11px] uppercase tracking-[0.06em] text-fm-muted">Uppercase label · 11px · muted</p>
        </div>
      </Panel>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="StatusBadge" subtitle="Never colour alone">
          <div className="flex flex-wrap gap-2">
            <StatusBadge verdict="approve" />
            <StatusBadge verdict="partial_pay" />
            <StatusBadge verdict="hold" />
            <StatusBadge verdict="hold" pulse />
            <StatusBadge verdict="human_review" />
            <StatusBadge fraud />
            <StatusBadge quality="reliable" />
            <StatusBadge quality="insufficient" />
          </div>
        </Panel>
        <Panel title="Money + Qty" subtitle="Paise in, Indian grouping out (en-IN)">
          <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 font-mono text-[13px] tabular-nums">
            <span className="text-fm-muted">₹0</span><Money paise={0} />
            <span className="text-fm-muted">999 paise</span><Money paise={99900} />
            <span className="text-fm-muted">Ledger total</span><Money paise={124500000} />
            <span className="text-fm-muted">At risk</span><span className="text-fm-hold"><Money paise={30720000} /></span>
            <span className="text-fm-muted">Ordered</span><Qty value={120} unit="box" />
            <span className="text-fm-muted">Observed</span><Qty value={10} unit="box" />
          </div>
        </Panel>
      </div>

      <Panel title="KpiTile" subtitle="Left signal bar + mono value">
        <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
          <KpiTile label="Payments held" value={14} delta="+3 today" tone="hold" />
          <KpiTile label="Verified" value={86} delta="86% of receipts" tone="verified" />
          <KpiTile label="Amount at risk" value={<Money paise={122000000} />} tone="fraud" hint="ex-GST" />
          <KpiTile label="Awaiting review" value={7} delta="oldest 2d" tone="review" />
        </div>
      </Panel>

      <Panel title="DataTable" subtitle="Dense 32px rows · sortable · mono numerals" padded={false} bodyClassName="p-0">
        <DataTable columns={columns} data={DEMO} className="border-0" />
      </Panel>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Stepper" subtitle="Persisted job states — SSE replays these" actions={
          <select value={step} onChange={(e) => setStep(e.target.value as JobStatus)} className="h-7 rounded-fm-sm border border-fm-border bg-fm-bg px-1.5 font-mono text-[11px]" aria-label="Preview step">
            {(["queued","uploading","understanding","tracking","damage_check","done","failed"] as JobStatus[]).map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        }>
          <Stepper current={step} />
          <div className="mt-4"><Stepper current="failed" failed /></div>
        </Panel>
        <Panel title="Buttons" subtitle="Radix Slot · 150ms">
          <div className="flex flex-wrap gap-2">
            <Button variant="primary">Approve payment</Button>
            <Button variant="hold">Hold payment</Button>
            <Button variant="danger">Flag fraud risk</Button>
            <Button variant="secondary">Export evidence</Button>
            <Button variant="ghost">Dismiss</Button>
            <Button disabled>Disabled</Button>
          </div>
        </Panel>
      </div>

      <Panel title="Chart tokens" subtitle="Recharts reads CSS vars — flat fills, hairline grid">
        <div className="h-44">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={CHART} margin={{ top: 4, right: 4, bottom: 0, left: -18 }} barGap={2}>
              <CartesianGrid stroke={chartColors.grid()} strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="day" tick={{ fill: chartColors.text(), fontSize: 11, fontFamily: "IBM Plex Mono" }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: chartColors.text(), fontSize: 11, fontFamily: "IBM Plex Mono" }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{ background: "var(--fm-raised)", border: "1px solid var(--fm-border)", borderRadius: 4, fontSize: 12 }} />
              <Bar dataKey="verified" name="Verified" fill={chartColors.verified()} radius={[2, 2, 0, 0]} />
              <Bar dataKey="holds" name="Holds" fill={chartColors.hold()} radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Panel>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="EmptyState">
          <EmptyState title="No cases match this filter" description="Deliveries that contradict the PO, GRN, or invoice will appear here." action={<Button size="sm">Clear filters</Button>} />
        </Panel>
        <Panel title="Skeleton" actions={<Button size="sm" onClick={() => setShowSkeleton((s) => !s)}>{showSkeleton ? "Hide" : "Show"}</Button>}>
          {showSkeleton ? <SkeletonRows rows={4} /> : (
            <div className="flex flex-col gap-2">
              <Skeleton className="h-4 w-2/3" />
              <Skeleton className="h-8 w-full" />
              <p className="text-[11px] text-fm-muted">Toggle to preview loading rows.</p>
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}
