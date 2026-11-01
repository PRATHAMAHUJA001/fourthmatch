/** Dock Live (home): the receiving queue, today's readouts, and the live pipeline bay. */
import { useQuery } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { LayoutGrid, Play, Plus, Rows3 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
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
import { cn } from "../lib/cn";
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

type QueueView = "cards" | "table";
const VIEW_KEY = "fm.dock.queueView";

function readView(): QueueView {
  try { return localStorage.getItem(VIEW_KEY) === "cards" ? "cards" : "table"; } catch { return "table"; }
}

function ViewToggle({ value, onChange }: { value: QueueView; onChange: (v: QueueView) => void }) {
  const opts: { v: QueueView; label: string; icon: typeof LayoutGrid }[] = [
    { v: "cards", label: "Cards", icon: LayoutGrid },
    { v: "table", label: "Table", icon: Rows3 },
  ];
  return (
    <div role="group" aria-label="Queue view" className="inline-flex overflow-hidden rounded-fm-sm border border-fm-border-strong">
      {opts.map(({ v, label, icon: Icon }, i) => (
        <button
          key={v} type="button" aria-pressed={value === v} onClick={() => onChange(v)}
          className={cn(
            "inline-flex h-6 items-center gap-1 px-2 font-cond text-[11px] font-semibold uppercase tracking-[0.06em] transition-colors duration-150",
            i > 0 && "border-l border-fm-border-strong",
            value === v ? "bg-fm-text text-fm-bg" : "text-fm-muted hover:bg-fm-hover hover:text-fm-text",
          )}
        >
          <Icon size={12} aria-hidden />{label}
        </button>
      ))}
    </div>
  );
}

function DeliveryCard({ r }: { r: Row }) {
  const types = r.discrepancy_types ?? [];
  const finding = types.length ? FINDING[types[0]] ?? types[0] : "All four sources agree";
  const held = r.held_paise > 0;
  return (
    <Link
      to={`/cases/${r.po_id}`}
      className={cn(
        "group flex min-w-0 flex-col gap-3 rounded-fm border bg-fm-panel p-3.5 transition-colors duration-150 hover:bg-fm-hover",
        held ? "border-fm-hold-line" : "border-fm-border",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate text-[13.5px] font-semibold tracking-[-0.01em]">{r.vendor_name}</div>
          <div className="mt-1 flex items-center gap-1.5">
            <span className="font-mono text-[11.5px] text-fm-muted">{r.po_number.replace("FM/PO/26-27/", "PO-")}</span>
            {r.evidence_source === "video" ? <Tag tone="info">VIDEO</Tag> : <Tag>DOCS</Tag>}
          </div>
        </div>
        <StatusBadge verdict={r.verdict} size="sm" />
      </div>
      <div>
        <div className="fm-label">Held</div>
        <Money paise={r.held_paise} className={cn("block text-[30px] font-medium leading-[1.05] tracking-[-0.04em]", held && "text-fm-hold")} />
      </div>
      <div className="mt-auto flex flex-wrap items-center gap-1.5 border-t border-fm-border pt-2.5">
        <span className={cn("min-w-0 flex-1 truncate text-[12px]", types.length ? "text-fm-muted" : "text-fm-faint")}>{finding}</span>
        {(r.clauses ?? []).map((c) => <Tag key={c} tone="hold">§{c}</Tag>)}
        <span className="font-mono text-[10.5px] text-fm-faint">{r.decided_at ? formatTs(r.decided_at).split(" · ")[1] : "—"}</span>
      </div>
    </Link>
  );
}

export function DockLive() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [dialog, setDialog] = useState(params.get("new") === "1");
  const replayPo = params.get("replay");
  const [run, setRun] = useState<{ deliveryId: number; poId: number } | null>(null);
  const [view, setViewState] = useState<QueueView>(readView);
  const setView = (v: QueueView) => { setViewState(v); try { localStorage.setItem(VIEW_KEY, v); } catch { /* storage unavailable */ } };
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
            <div className="flex flex-col items-end gap-3">
              <BigClock />
              <div className="flex gap-2">
              <Button variant="secondary" onClick={() => void startReplay(4)}><Play size={13} /> Replay mixed load</Button>
              <Button variant="accent" onClick={() => setDialog(true)}><Plus size={14} /> New delivery</Button>
              </div>
            </div>
          </div>
        )}
      </Panel>

      <Panel
        index="02"
        title="Receiving queue"
        subtitle={cases.data ? `${cases.data.length} deliveries` : undefined}
        actions={
          <>
            {view === "table"
              ? <span className="flex items-center gap-1 text-[11px] text-fm-faint max-sm:hidden"><Kbd>J</Kbd><Kbd>K</Kbd> move <Kbd>↵</Kbd> open</span>
              : <span className="flex items-center gap-1 text-[11px] text-fm-faint max-sm:hidden"><Kbd>Tab</Kbd> move <Kbd>↵</Kbd> open</span>}
            <ViewToggle value={view} onChange={setView} />
          </>
        }
        padded={false}
      >
        {cases.isLoading ? <SkeletonRows rows={8} className="p-3" /> : cases.isError ? (
          <ErrorState message={cases.error instanceof Error ? cases.error.message : "Could not load the queue."} />
        ) : view === "cards" ? (
          <div className="grid gap-3 p-3 sm:grid-cols-2 xl:grid-cols-3" aria-label="Receiving queue">
            {rows.map((r) => <DeliveryCard key={r.po_id} r={r} />)}
          </div>
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

function BigClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => { const t = setInterval(() => setNow(new Date()), 1000); return () => clearInterval(t); }, []);
  const [hm, sec] = [now.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Asia/Kolkata" }), now.toLocaleTimeString("en-IN", { second: "2-digit", timeZone: "Asia/Kolkata" }).padStart(2, "0")];
  return (
    <div className="text-right max-md:hidden" aria-label="Dock time">
      <span className="font-mono text-[52px] font-medium leading-none tracking-[-0.06em] tabular-nums">{hm}</span>
      <span className="ml-1 font-mono text-[18px] tabular-nums text-fm-faint">{sec}</span>
      <div className="fm-label mt-1">IST · dock clock</div>
    </div>
  );
}
