/** Receiving dock (home of the app): live status, today's readouts, the bay where a delivery is
 *  verified live, and the receiving queue. The replay (/dock?replay=<po>) is the demo recording. */
import { useQuery } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { LayoutGrid, List, Play, Plus } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { NewDeliveryDialog } from "../components/evidence/NewDeliveryDialog";
import { PipelineRun } from "../components/evidence/PipelineRun";
import { Button } from "../components/ui/Button";
import { DataTable } from "../components/ui/DataTable";
import { DeliveryThumb } from "../components/ui/DeliveryThumb";
import { ErrorState, Skeleton, SkeletonRows } from "../components/ui/EmptyState";
import { KpiStrip, KpiTile } from "../components/ui/KpiTile";
import { Money } from "../components/ui/Money";
import { StatusBadge } from "../components/ui/StatusBadge";
import { Kbd } from "../components/ui/Tag";
import { api } from "../lib/api";
import { cn } from "../lib/cn";
import { formatINR, formatTs } from "../lib/format";
import type { CaseSummary } from "../types/api";

const FINDING: Record<string, string> = {
  grn_contradicted_by_video: "GRN contradicted by video",
  short_shipment_beyond_tolerance: "Short shipment",
  damaged_units_invoiced: "Damaged units invoiced",
  invoice_price_above_po: "Price above PO",
  invoice_qty_exceeds_po: "Invoice qty above PO",
  duplicate_invoice_number: "Duplicate invoice",
};
const finding = (r: CaseSummary) => {
  const t = r.discrepancy_types ?? [];
  return t.length ? FINDING[t[0]] ?? t[0].replaceAll("_", " ") : "All four sources agree";
};
const time = (iso: string | null | undefined) => (iso ? formatTs(iso).split(" · ")[1] : "—");

const columns: ColumnDef<CaseSummary, unknown>[] = [
  {
    id: "delivery", header: "Delivery", accessorFn: (r) => r.vendor_name,
    cell: ({ row }) => {
      const r = row.original;
      return (
        <div className="flex items-center gap-4 py-2">
          <DeliveryThumb c={r} className="h-11 w-[72px] rounded-[10px]" />
          <div className="min-w-0">
            <div className="max-w-[260px] truncate text-[15px] font-semibold max-md:max-w-[220px] tracking-[-0.012em]">{r.vendor_name}</div>
            <div className="mt-0.5 text-[13px] text-fm-muted">
              <span className="font-mono text-[12.5px]">{r.po_number}</span>
              <span className="ml-2 text-fm-faint max-md:hidden">{r.evidence_source === "video" ? "Video" : "Documents"}</span>
            </div>
            <div className="mt-1.5 flex items-center gap-2 md:hidden">
              <StatusBadge verdict={r.verdict} size="sm" />
              {r.held_paise > 0 && <Money paise={r.held_paise} className="text-[13px] font-medium text-fm-hold" />}
            </div>
          </div>
        </div>
      );
    },
  },
  {
    id: "why", header: "Finding", enableSorting: false, meta: { className: "max-md:hidden" },
    cell: ({ row }) => (
      <div className="min-w-0">
        <div className={cn("max-w-[240px] truncate text-[14px]", (row.original.discrepancy_types ?? []).length ? "text-fm-text" : "text-fm-faint")}>{finding(row.original)}</div>
        {(row.original.clauses ?? []).length > 0 && <div className="text-[12px] text-fm-muted">Clause {(row.original.clauses ?? []).join(", ")}</div>}
      </div>
    ),
  },
  { accessorKey: "verdict", header: "Status", meta: { className: "max-md:hidden" }, cell: ({ row }) => <StatusBadge verdict={row.original.verdict} size="sm" /> },
  {
    accessorKey: "held_paise", header: "Held", meta: { align: "right", className: "max-md:hidden" },
    cell: ({ row }) => <Money paise={row.original.held_paise} className={cn("text-[14px]", row.original.held_paise > 0 && "font-medium text-fm-hold")} />,
  },
  {
    id: "time", header: "Decided", accessorFn: (r) => r.decided_at ?? "", meta: { align: "right", width: "96px", className: "max-md:hidden" },
    cell: ({ row }) => <span className="font-mono text-[12.5px] text-fm-muted">{time(row.original.decided_at)}</span>,
  },
];

type QueueView = "cards" | "table";
const VIEW_KEY = "fm.dock.queueView";

function readView(): QueueView {
  try { return localStorage.getItem(VIEW_KEY) === "cards" ? "cards" : "table"; } catch { return "table"; }
}

function ViewToggle({ value, onChange }: { value: QueueView; onChange: (v: QueueView) => void }) {
  const opts: { v: QueueView; label: string; icon: typeof LayoutGrid }[] = [
    { v: "table", label: "List", icon: List },
    { v: "cards", label: "Grid", icon: LayoutGrid },
  ];
  return (
    <div role="group" aria-label="Queue view" className="inline-flex rounded-full bg-fm-hover/70 p-0.5">
      {opts.map(({ v, label, icon: Icon }) => (
        <button
          key={v} type="button" aria-pressed={value === v} onClick={() => onChange(v)}
          className={cn(
            "inline-flex h-8 items-center gap-1.5 rounded-full px-3.5 text-[13px] font-medium transition-colors duration-200",
            value === v ? "fm-thumb text-fm-text" : "text-fm-muted hover:text-fm-text",
          )}
        >
          <Icon size={14} aria-hidden />{label}
        </button>
      ))}
    </div>
  );
}

function DeliveryCard({ r }: { r: CaseSummary }) {
  const held = r.held_paise > 0;
  return (
    <Link to={`/cases/${r.po_id}`} className="group flex min-w-0 flex-col overflow-hidden rounded-fm bg-fm-panel transition-transform duration-300 ease-[var(--fm-ease)] hover:-translate-y-0.5">
      <DeliveryThumb c={r} className="aspect-[16/9] w-full" />
      <div className="flex flex-1 flex-col p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="truncate text-[17px] font-semibold tracking-[-0.016em]">{r.vendor_name}</div>
            <div className="mt-0.5 font-mono text-[12.5px] text-fm-muted">{r.po_number}</div>
          </div>
          <StatusBadge verdict={r.verdict} size="sm" />
        </div>
        <div className="mt-5 flex items-end justify-between gap-3">
          <div className="min-w-0">
            <div className={cn("fm-figure text-[32px] leading-none", held ? "text-fm-hold" : "text-fm-faint")}>{formatINR(r.held_paise)}</div>
            <div className="mt-1.5 truncate text-[13px] text-fm-muted">{held ? "held · " : ""}{finding(r)}</div>
          </div>
          <span className="shrink-0 font-mono text-[12px] text-fm-faint">{time(r.decided_at)}</span>
        </div>
      </div>
    </Link>
  );
}

function IdleBay({ onReplay, onReplayMixed, onNew }: { onReplay?: () => void; onReplayMixed?: () => void; onNew: () => void }) {
  return (
    <section className="relative overflow-hidden rounded-fm-xl bg-black text-white" aria-label="Bay 01">
      <img src="/media/hero_poster.webp" alt="Receiving bay camera view: cartons on the dock floor" width={1280} height={720} className="absolute inset-0 h-full w-full object-cover opacity-80" />
      <div className="absolute inset-0 bg-[linear-gradient(90deg,rgba(0,0,0,0.78)_0%,rgba(0,0,0,0.5)_42%,rgba(0,0,0,0.05)_80%)] max-md:bg-[linear-gradient(0deg,rgba(0,0,0,0.85)_0%,rgba(0,0,0,0.45)_60%,rgba(0,0,0,0.2)_100%)]" aria-hidden />
      <div className="relative flex min-h-[420px] flex-col justify-end p-12 max-md:min-h-[460px] max-md:p-6">
        <p className="flex items-center gap-2 text-[15px] font-semibold text-white/75"><span className="h-2 w-2 rounded-full bg-white/60" aria-hidden />Bay 01 · idle</p>
        <h2 className="mt-3 max-w-[16ch] text-[48px] font-bold leading-[1.04] tracking-[-0.034em] max-md:text-[34px]">Waiting for the next truck.</h2>
        <p className="mt-4 max-w-[46ch] text-[17px] leading-relaxed text-white/80">
          Start a delivery and watch it decide: Muse Spark reads the footage, SAM 3.1 tracks every unit, Python reconciles four sources, and the agent applies your policy.
        </p>
        <div className="mt-8 flex flex-wrap gap-3">
          {onReplay && <Button variant="accent" size="xl" onClick={onReplay}><Play size={15} fill="currentColor" /> Replay a short shipment</Button>}
          {onReplayMixed && <Button size="xl" className="bg-white/15 text-white backdrop-blur-md hover:bg-white/25" onClick={onReplayMixed}>Replay a mixed load</Button>}
          <Button size="xl" variant="ghost" className="text-white/85 hover:bg-white/10 hover:text-white" onClick={onNew}><Plus size={16} /> New delivery</Button>
        </div>
      </div>
      <DockClock />
    </section>
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

  // ?replay=<po_id> from the command palette / landing page. Started once, then the param is dropped.
  const replayedRef = useRef(false);
  useEffect(() => {
    if (!replayPo || replayedRef.current) return;
    replayedRef.current = true;
    void startReplay(Number(replayPo));
    const next = new URLSearchParams(params);
    next.delete("replay");
    setParams(next, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [replayPo]);

  const rows = useMemo(
    () => (cases.data ?? []).slice().sort((a, b) => (b.decided_at ?? "").localeCompare(a.decided_at ?? "")),
    [cases.data],
  );
  const shortPo = rows.find((c) => c.scenario_id === "scn2_short")?.po_id;
  const mixedPo = rows.find((c) => c.scenario_id === "scn4_mixed")?.po_id;
  const k = kpis.data;

  return (
    <div className="flex flex-col">
      <div className="mb-10 flex flex-wrap items-end justify-between gap-x-6 gap-y-5 pt-6 max-sm:mb-8 max-sm:pt-2">
        <div className="min-w-0 max-w-3xl">
          <p className="flex items-center gap-2 text-[15px] font-semibold text-fm-muted">
            <span className={cn("h-2 w-2 rounded-full", run ? "fm-live-dot bg-fm-accent" : "bg-fm-verified-fill")} aria-hidden />
            {run ? "Live · verifying a delivery at Bay 01" : "Live · Plant 01 receiving"}
          </p>
          <h1 className="mt-2 text-[52px] font-bold leading-[1.02] tracking-[-0.036em] max-sm:text-[40px]">Receiving dock</h1>
          <p className="mt-3 max-w-[52ch] text-[19px] leading-snug tracking-[-0.014em] text-fm-muted max-sm:text-[17px]">
            Every truck is checked against its PO, GRN and invoice, and against the camera, before payment goes out.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="accent" size="lg" onClick={() => setDialog(true)}><Plus size={16} /> New delivery <Kbd className="ml-1 bg-white/20 text-white shadow-none">N</Kbd></Button>
        </div>
      </div>

      {kpis.isLoading ? <Skeleton className="h-[148px] rounded-fm" /> : k ? (
        <KpiStrip className="grid-cols-2 md:grid-cols-4 max-md:divide-x [&>*:nth-child(3)]:max-md:border-l-0">
          <KpiTile label="Held today" value={formatINR(k.held_today_paise)} tone="hold" hint="Debit notes and holds" />
          <KpiTile label="Verified" value={k.deliveries_verified} unit={`of ${k.deliveries_total}`} tone="verified" hint="Paid in full" />
          <KpiTile label="Discrepancy rate" value={k.discrepancy_rate_pct.toFixed(1)} unit="%" hint="Deliveries with a mismatch" />
          <KpiTile label="Time to verdict" value={k.avg_time_to_verdict_s ?? "—"} unit={k.avg_time_to_verdict_s != null ? "s" : undefined} hint={k.avg_time_to_verdict_s != null ? "Upload to recorded decision" : "Measured from live job timings"} />
        </KpiStrip>
      ) : null}

      <div className="mt-6">
        {run ? (
          <PipelineRun key={run.deliveryId} deliveryId={run.deliveryId} poId={run.poId} onReset={() => setRun(null)} />
        ) : (
          <IdleBay
            onReplay={shortPo != null ? () => void startReplay(shortPo) : undefined}
            onReplayMixed={mixedPo != null ? () => void startReplay(mixedPo) : undefined}
            onNew={() => setDialog(true)}
          />
        )}
      </div>

      <section className="mt-16 max-sm:mt-12" aria-labelledby="queue-title">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 id="queue-title" className="text-[32px] font-bold tracking-[-0.03em] max-sm:text-[28px]">Receiving queue</h2>
            <p className="mt-1 text-[15px] text-fm-muted">{cases.data ? `${cases.data.length} deliveries, newest first` : " "}</p>
          </div>
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-1 text-[12px] text-fm-faint max-md:hidden">
              {view === "table" ? <><Kbd>J</Kbd><Kbd>K</Kbd> move <Kbd>↵</Kbd> open</> : <><Kbd>Tab</Kbd> move <Kbd>↵</Kbd> open</>}
            </span>
            <ViewToggle value={view} onChange={setView} />
          </div>
        </div>
        {cases.isLoading ? <div className="rounded-fm bg-fm-panel p-4"><SkeletonRows rows={8} /></div> : cases.isError ? (
          <div className="rounded-fm bg-fm-panel"><ErrorState message={cases.error instanceof Error ? cases.error.message : "Could not load the queue."} /></div>
        ) : view === "cards" ? (
          <div className="grid gap-6 sm:grid-cols-2 xl:grid-cols-3" aria-label="Receiving queue">
            {rows.map((r) => <DeliveryCard key={r.po_id} r={r} />)}
          </div>
        ) : (
          <div className="overflow-hidden rounded-fm bg-fm-panel px-2 py-1">
            <DataTable columns={columns} data={rows} keyboard onRowClick={(r) => navigate(`/cases/${r.po_id}`)} label="Receiving queue" rowHeight="auto" />
          </div>
        )}
      </section>

      <NewDeliveryDialog open={dialog} onOpenChange={(o) => { setDialog(o); if (!o && params.get("new")) { const n = new URLSearchParams(params); n.delete("new"); setParams(n, { replace: true }); } }} onStarted={(deliveryId, poId) => setRun({ deliveryId, poId })} />
      <NKey onPress={() => setDialog(true)} />
    </div>
  );
}

function NKey({ onPress }: { onPress: () => void }) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || e.metaKey || e.ctrlKey) return;
      if (e.key === "n") { e.preventDefault(); onPress(); }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onPress]);
  return null;
}

function DockClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => { const t = setInterval(() => setNow(new Date()), 1000); return () => clearInterval(t); }, []);
  const hm = now.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Asia/Kolkata" });
  return (
    <span className="absolute right-6 top-6 rounded-full bg-black/45 px-3.5 py-1.5 font-mono text-[13px] tabular-nums text-white backdrop-blur-md max-md:right-4 max-md:top-4" aria-label="Dock time">
      {hm} IST
    </span>
  );
}
