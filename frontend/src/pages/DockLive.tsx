/** Dock Live (home): the receiving queue, today's readouts, and the live pipeline bay. */
import { useQuery } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { Play, Plus } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { NewDeliveryDialog } from "../components/evidence/NewDeliveryDialog";
import { PipelineRun } from "../components/evidence/PipelineRun";
import { Button } from "../components/ui/Button";
import { DataTable } from "../components/ui/DataTable";
import { ErrorState, Skeleton, SkeletonRows } from "../components/ui/EmptyState";
import { KpiStrip, KpiTile } from "../components/ui/KpiTile";
import { Money } from "../components/ui/Money";
import { PageHeader, Panel } from "../components/ui/Panel";
import { StatusBadge } from "../components/ui/StatusBadge";
import { Kbd, Tag } from "../components/ui/Tag";
import { BrandMark } from "../components/shell/BrandMark";
import { api } from "../lib/api";
import { formatINR, formatTs } from "../lib/format";
import type { CaseSummary } from "../types/api";

type Row = CaseSummary & { bay: string };

const columns: ColumnDef<Row, unknown>[] = [
  {
    id: "time", header: "Decided", accessorFn: (r) => r.decided_at ?? "",
    cell: ({ row }) => <span className="font-mono text-[11.5px] text-fm-muted">{row.original.decided_at ? formatTs(row.original.decided_at).split(" · ")[1] : "—"}</span>,
    meta: { width: "72px" },
  },
  {
    accessorKey: "po_number", header: "PO",
    cell: ({ row }) => (
      <div className="flex items-center gap-2">
        <span className="font-mono">{row.original.po_number.replace("FM/PO/26-27/", "PO-")}</span>
        {row.original.evidence_source === "video" ? <Tag tone="info">VIDEO</Tag> : <Tag>DOCS</Tag>}
      </div>
    ),
  },
  { accessorKey: "vendor_name", header: "Vendor", cell: ({ row }) => <span className="block max-w-[220px] truncate">{row.original.vendor_name}</span> },
  {
    id: "why", header: "Finding", enableSorting: false,
    cell: ({ row }) => {
      const t = row.original.discrepancy_types ?? [];
      return t.length ? (
        <span className="flex items-center gap-1.5">
          <span className="max-w-[220px] truncate text-fm-muted">{FINDING[t[0]] ?? t[0]}</span>
          {(row.original.clauses ?? []).map((c) => <Tag key={c} tone="hold">§{c}</Tag>)}
        </span>
      ) : <span className="text-fm-faint">All four sources agree</span>;
    },
  },
  { accessorKey: "verdict", header: "Status", cell: ({ row }) => <StatusBadge verdict={row.original.verdict} size="sm" /> },
  {
    accessorKey: "held_paise", header: "Held", meta: { align: "right" },
    cell: ({ row }) => <Money paise={row.original.held_paise} className={row.original.held_paise > 0 ? "text-fm-hold" : undefined} />,
  },
];

const FINDING: Record<string, string> = {
  grn_contradicted_by_video: "GRN contradicted by video",
  short_shipment_beyond_tolerance: "Short shipment",
  damaged_units_invoiced: "Damaged units invoiced",
  invoice_price_above_po: "Price above PO",
  invoice_qty_exceeds_po: "Invoice qty above PO",
  duplicate_invoice_number: "Duplicate invoice",
};

export function DockLive() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [dialog, setDialog] = useState(params.get("new") === "1");
  const replayPo = params.get("replay");
  const [run, setRun] = useState<{ deliveryId: number; poId: number } | null>(null);
  const cases = useQuery({ queryKey: ["cases"], queryFn: api.cases });
  const kpis = useQuery({ queryKey: ["dock-kpis"], queryFn: api.dockKpis });

  const startReplay = async (poId: number) => {
    const r = await api.createDelivery(poId, null);
    setRun({ deliveryId: r.delivery_id, poId });
  };

  // ?replay=<po_id> from the command palette / landing page
  const [replayed, setReplayed] = useState(false);
  if (replayPo && !replayed) {
    setReplayed(true);
    void startReplay(Number(replayPo));
    const next = new URLSearchParams(params);
    next.delete("replay");
    setParams(next, { replace: true });
  }

  const rows: Row[] = useMemo(
    () => (cases.data ?? []).slice().sort((a, b) => (b.decided_at ?? "").localeCompare(a.decided_at ?? "")).map((c, i) => ({ ...c, bay: `B${(i % 3) + 1}` })),
    [cases.data],
  );
  const heldSpark = useMemo(() => rows.slice().reverse().reduce<number[]>((acc, r) => [...acc, (acc.at(-1) ?? 0) + r.held_paise], []), [rows]);
  const k = kpis.data;

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        eyebrow={<span className="flex items-center gap-1.5"><span className="fm-live-dot h-1.5 w-1.5 rounded-full bg-fm-verified" />Plant 01 · Receiving · Live</span>}
        title="Dock Live"
        meta={<span>Every delivery is checked against its PO, GRN and invoice and the dock video before payment goes out.</span>}
        actions={
          <>
            <Button variant="secondary" size="md" onClick={() => void startReplay(2)}><Play size={13} /> Replay short shipment</Button>
            <Button variant="accent" size="md" onClick={() => setDialog(true)}><Plus size={14} /> New delivery <Kbd className="ml-1 border-black/20 bg-black/10 text-fm-ink">N</Kbd></Button>
          </>
        }
      />

      {kpis.isLoading ? <Skeleton className="h-[104px]" /> : k ? (
        <KpiStrip className="grid-cols-2 md:grid-cols-4">
          <KpiTile label="Held today" value={formatINR(k.held_today_paise)} tone="hold" spark={heldSpark} hint="pending debit notes + holds" />
          <KpiTile label="Verified" value={k.deliveries_verified} unit={`of ${k.deliveries_total}`} tone="verified" hint="paid in full" />
          <KpiTile label="Discrepancy rate" value={k.discrepancy_rate_pct.toFixed(1)} unit="%" hint="deliveries with a mismatch" />
          <KpiTile label="Time to verdict" value={k.avg_time_to_verdict_s ?? "—"} unit={k.avg_time_to_verdict_s != null ? "s avg" : undefined} hint={k.avg_time_to_verdict_s != null ? "upload → recorded decision" : "measured from job timings in live mode"} />
        </KpiStrip>
      ) : null}

      <Panel
        index="01"
        title="Bay 01 · Pipeline"
        subtitle={run ? "verifying delivery" : "idle"}
        actions={run ? <Tag tone="info">delivery #{run.deliveryId}</Tag> : undefined}
        bodyClassName={run ? "p-3" : "p-0"}
      >
        {run ? (
          <PipelineRun key={run.deliveryId} deliveryId={run.deliveryId} poId={run.poId} onReset={() => setRun(null)} />
        ) : (
          <div className="fm-dotgrid grid items-center gap-6 px-6 py-8 md:grid-cols-[1fr_auto]">
            <div className="flex items-start gap-4">
              <BrandMark size={34} />
              <div>
                <p className="text-[15px] font-medium">Bay is idle. Waiting for the next truck.</p>
                <p className="mt-1 max-w-xl text-[12.5px] text-fm-muted">
                  Start a delivery and watch it live: Muse Spark reads the footage, SAM 3.1 tracks every unit, Python reconciles the four sources and the decision agent applies your policy.
                </p>
              </div>
            </div>
            <div className="flex gap-2">
              <Button variant="secondary" onClick={() => void startReplay(4)}><Play size={13} /> Replay mixed load</Button>
              <Button variant="accent" onClick={() => setDialog(true)}><Plus size={14} /> New delivery</Button>
            </div>
          </div>
        )}
      </Panel>

      <Panel
        index="02"
        title="Receiving queue"
        subtitle={cases.data ? `${cases.data.length} deliveries` : undefined}
        actions={<span className="flex items-center gap-1 text-[11px] text-fm-faint"><Kbd>J</Kbd><Kbd>K</Kbd> move <Kbd>↵</Kbd> open</span>}
        padded={false}
      >
        {cases.isLoading ? <SkeletonRows rows={8} className="p-3" /> : cases.isError ? (
          <ErrorState message={cases.error instanceof Error ? cases.error.message : "Could not load the queue."} />
        ) : (
          <DataTable columns={columns} data={rows} keyboard onRowClick={(r) => navigate(`/cases/${r.po_id}`)} label="Receiving queue" />
        )}
      </Panel>

      <NewDeliveryDialog open={dialog} onOpenChange={(o) => { setDialog(o); if (!o && params.get("new")) { const n = new URLSearchParams(params); n.delete("new"); setParams(n, { replace: true }); } }} onStarted={(deliveryId, poId) => setRun({ deliveryId, poId })} />
      <NKey onPress={() => setDialog(true)} />
    </div>
  );
}

function NKey({ onPress }: { onPress: () => void }) {
  useNKey(onPress);
  return null;
}

function useNKey(fn: () => void) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || e.metaKey || e.ctrlKey) return;
      if (e.key === "n") { e.preventDefault(); fn(); }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [fn]);
}
