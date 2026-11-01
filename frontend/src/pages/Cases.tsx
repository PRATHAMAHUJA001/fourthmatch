/** Cases ledger: every payment decision, filterable, keyboard-navigable. */
import { useQuery } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { Search } from "lucide-react";
import { useMemo } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { DataTable } from "../components/ui/DataTable";
import { EmptyState, ErrorState, Skeleton, SkeletonRows } from "../components/ui/EmptyState";
import { KpiStrip, KpiTile } from "../components/ui/KpiTile";
import { Money } from "../components/ui/Money";
import { PageHeader, Panel } from "../components/ui/Panel";
import { StatusBadge } from "../components/ui/StatusBadge";
import { Kbd } from "../components/ui/Tag";
import { Button } from "../components/ui/Button";
import { DeliveryThumb } from "../components/ui/DeliveryThumb";
import { api } from "../lib/api";
import { formatINR, formatTs } from "../lib/format";
import type { CaseSummary, Verdict } from "../types/api";
import { VERDICT_LABEL } from "../types/api";
import { Segmented } from "./cases/Segmented";

const DISCREPANCY_LABEL: Record<string, string> = {
  grn_contradicted_by_video: "GRN contradicted by video",
  short_shipment_beyond_tolerance: "Short shipment",
  damaged_units_invoiced: "Damaged units invoiced",
  invoice_price_above_po: "Price above PO",
  invoice_qty_exceeds_po: "Invoice qty above PO",
  duplicate_invoice_number: "Duplicate invoice",
};
const discrepancyText = (t: string) => DISCREPANCY_LABEL[t] ?? t.replaceAll("_", " ");

type VerdictFilter = "all" | Verdict;
type SourceFilter = "all" | "video" | "document";
const VERDICT_KEYS: Verdict[] = ["approve", "partial_pay", "hold", "human_review"];

const isVideo = (c: CaseSummary) => c.evidence_source === "video";
const isDocs = (c: CaseSummary) => c.evidence_source === "document";

const columns: ColumnDef<CaseSummary, unknown>[] = [
  {
    id: "po",
    accessorFn: (c) => c.po_number,
    header: "Delivery",
    cell: ({ row }) => (
      <div className="flex items-center gap-4 py-2">
        <DeliveryThumb c={row.original} className="h-11 w-[72px] rounded-[10px]" />
        <div className="min-w-0 leading-tight">
          <div className="max-w-[240px] truncate text-[15px] font-semibold max-md:max-w-[220px] tracking-[-0.012em]">{row.original.vendor_name}</div>
          <div className="mt-1 flex items-center gap-2 text-[13px] text-fm-muted">
            <span className="font-mono text-[12.5px]">{row.original.po_number}</span>
            <span className="text-fm-faint max-md:hidden">{isVideo(row.original) ? "Video" : isDocs(row.original) ? "Documents" : "—"}</span>
          </div>
          <div className="mt-1.5 flex items-center gap-2 md:hidden">
            <StatusBadge verdict={row.original.verdict} size="sm" />
            {row.original.held_paise > 0 && <Money paise={row.original.held_paise} className="text-[13px] font-medium text-fm-hold" />}
          </div>
        </div>
      </div>
    ),
  },
  {
    id: "discrepancy",
    accessorFn: (c) => (c.discrepancy_types ?? []).map(discrepancyText).join(", "),
    header: "Discrepancy",
    meta: { className: "max-md:hidden" },
    cell: ({ row }) => {
      const t = row.original.discrepancy_types ?? [];
      const cl = row.original.clauses ?? [];
      if (t.length === 0) return <span className="text-fm-faint">None</span>;
      return (
        <div className="min-w-0 leading-tight">
          <div className="max-w-[260px] truncate text-[14px]" title={t.map(discrepancyText).join(", ")}>
            {discrepancyText(t[0])}
            {t.length > 1 && <span className="ml-1.5 text-[12px] text-fm-faint">+{t.length - 1} more</span>}
          </div>
          {cl.length > 0 && <div className="mt-1 text-[12px] text-fm-muted">Clause {cl.join(", ")}</div>}
        </div>
      );
    },
  },
  {
    id: "verdict",
    accessorFn: (c) => c.verdict ?? "",
    header: "Verdict",
    meta: { className: "max-md:hidden" },
    cell: ({ row }) => <StatusBadge verdict={row.original.verdict} />,
  },
  {
    id: "held",
    accessorFn: (c) => c.held_paise,
    header: "Held",
    meta: { align: "right", className: "max-md:hidden" },
    cell: ({ row }) => <Money paise={row.original.held_paise} className={row.original.held_paise > 0 ? "font-medium text-fm-hold" : undefined} />,
  },
  {
    id: "decided",
    accessorFn: (c) => c.decided_at ?? "",
    header: "Decided",
    meta: { align: "right", className: "max-lg:hidden" },
    cell: ({ row }) => (row.original.decided_at ? <span className="text-[13px] tabular-nums text-fm-muted">{formatTs(row.original.decided_at)}</span> : <span className="text-fm-faint">—</span>),
  },
];

export function Cases() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const { data, isLoading, isError, error, refetch } = useQuery({ queryKey: ["cases"], queryFn: api.cases });

  const verdict = (params.get("verdict") ?? "all") as VerdictFilter;
  const source = (params.get("source") ?? "all") as SourceFilter;
  const q = params.get("q") ?? "";

  function setParam(key: string, value: string, empty: string) {
    setParams((prev) => {
      const next = new URLSearchParams(prev);
      if (value === empty) next.delete(key); else next.set(key, value);
      return next;
    }, { replace: true });
  }

  const rows = useMemo(() => data ?? [], [data]);
  const kpi = useMemo(() => {
    const held = rows.reduce((s, c) => s + c.held_paise, 0);
    const heldCases = rows.filter((c) => c.verdict === "hold" || c.verdict === "partial_pay").length;
    const verified = rows.filter((c) => c.verdict === "approve").length;
    const video = rows.filter(isVideo).length;
    const docs = rows.filter(isDocs).length;
    return { held, heldCases, verified, video, docs };
  }, [rows]);

  const counts = useMemo(() => {
    const m: Record<string, number> = { all: rows.length };
    for (const v of VERDICT_KEYS) m[v] = rows.filter((c) => c.verdict === v).length;
    return m;
  }, [rows]);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return rows.filter((c) => {
      if (verdict !== "all" && c.verdict !== verdict) return false;
      if (source === "video" && !isVideo(c)) return false;
      if (source === "document" && !isDocs(c)) return false;
      if (!needle) return true;
      const hay = [
        c.po_number, c.vendor_name, c.scenario_id ?? "",
        ...(c.clauses ?? []).flatMap((cl) => [cl, `§${cl}`]),
        ...(c.discrepancy_types ?? []).map(discrepancyText),
      ].join(" ").toLowerCase();
      return hay.includes(needle);
    });
  }, [rows, verdict, source, q]);

  const filtersActive = verdict !== "all" || source !== "all" || q !== "";

  return (
    <div>
      <PageHeader
        eyebrow="Ledger"
        title="Cases"
        meta={isLoading ? <Skeleton className="h-4 w-64" /> : (
          <span>{rows.length} payment decisions, {kpi.heldCases} on hold or partial.</span>
        )}
      />

      <KpiStrip className="mb-10 grid-cols-2 md:grid-cols-4 max-md:divide-x [&>*:nth-child(3)]:max-md:border-l-0 max-sm:mb-8">
        <KpiTile label="Total held" tone="hold" value={isLoading ? "—" : formatINR(kpi.held)} hint="Withheld across cases" />
        <KpiTile label="On hold or partial" value={isLoading ? "—" : kpi.heldCases} unit={`of ${rows.length}`} hint="Not released in full" />
        <KpiTile label="Verified" tone="verified" value={isLoading ? "—" : kpi.verified} unit={`of ${rows.length}`} hint="Documents and dock agree" />
        <KpiTile label="Video / paper only" value={isLoading ? "—" : `${kpi.video} / ${kpi.docs}`} hint="Evidence source per case" />
      </KpiStrip>

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Segmented
          label="Verdict"
          value={verdict}
          onChange={(v) => setParam("verdict", v, "all")}
          options={[
            { value: "all", label: "All", count: counts.all },
            ...VERDICT_KEYS.map((v) => ({ value: v, label: VERDICT_LABEL[v], count: counts[v] })),
          ]}
        />
        <Segmented
          label="Evidence source"
          value={source}
          onChange={(v) => setParam("source", v, "all")}
          options={[
            { value: "all", label: "Any evidence" },
            { value: "video", label: "Video", count: kpi.video },
            { value: "document", label: "Documents", count: kpi.docs },
          ]}
        />
        <label className="relative ml-auto flex w-full items-center sm:w-72">
          <Search size={15} className="pointer-events-none absolute left-3.5 text-fm-faint" aria-hidden />
          <span className="sr-only">Filter by PO, vendor or clause</span>
          <input
            type="search"
            value={q}
            onChange={(e) => setParam("q", e.target.value, "")}
            placeholder="PO, vendor, clause"
            className="fm-field h-10 w-full rounded-full bg-fm-panel pl-10 pr-4 text-[14px]"
          />
        </label>
      </div>

      <Panel padded={false} bodyClassName="flex flex-col px-2 pt-1">
        {isLoading ? (
          <SkeletonRows rows={7} className="p-4" />
        ) : isError ? (
          <ErrorState message={error instanceof Error ? error.message : "Could not load cases."} action={<Button size="md" variant="secondary" onClick={() => void refetch()}>Retry</Button>} />
        ) : rows.length === 0 ? (
          <EmptyState title="No cases yet" description="Cases appear once a delivery has been checked against its PO." />
        ) : (
          <DataTable
            label="Cases"
            columns={columns}
            data={filtered}
            keyboard
            rowHeight="auto"
            initialSorting={[{ id: "held", desc: true }]}
            emptyMessage={filtersActive ? "No cases match these filters." : "No cases"}
            onRowClick={(c) => navigate(`/cases/${c.po_id}`)}
          />
        )}

        <div className="flex items-center gap-1.5 border-t border-fm-border px-4 py-3 text-[12px] text-fm-faint">
          <Kbd>j</Kbd><Kbd>k</Kbd> to move, <Kbd>Enter</Kbd> to open
          {filtersActive && (
            <button type="button" className="ml-auto text-[13px] text-fm-accent-text hover:underline underline-offset-4" onClick={() => setParams({}, { replace: true })}>
              Clear filters
            </button>
          )}
        </div>
      </Panel>
    </div>
  );
}
