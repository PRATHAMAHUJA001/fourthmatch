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
import { Kbd, Tag } from "../components/ui/Tag";
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
    header: "PO",
    cell: ({ row }) => (
      <div className="flex flex-col leading-tight">
        <span className="font-mono text-[12.5px] font-medium">{row.original.po_number}</span>
        {row.original.scenario_id && <span className="font-mono text-[10.5px] text-fm-faint">{row.original.scenario_id}</span>}
      </div>
    ),
  },
  { id: "vendor", accessorFn: (c) => c.vendor_name, header: "Vendor", cell: ({ row }) => <span className="block max-w-[200px] truncate">{row.original.vendor_name}</span> },
  {
    id: "evidence",
    accessorFn: (c) => c.evidence_source ?? "none",
    header: "Evidence",
    cell: ({ row }) =>
      isVideo(row.original) ? <Tag tone="info">VIDEO</Tag> : isDocs(row.original) ? <Tag>DOCS</Tag> : <span className="font-mono text-fm-faint">—</span>,
  },
  {
    id: "discrepancy",
    accessorFn: (c) => (c.discrepancy_types ?? []).map(discrepancyText).join(", "),
    header: "Discrepancy",
    cell: ({ row }) => {
      const t = row.original.discrepancy_types ?? [];
      if (t.length === 0) return <span className="text-fm-faint">None</span>;
      return (
        <span className="block max-w-[260px] truncate text-fm-text" title={t.map(discrepancyText).join(", ")}>
          {discrepancyText(t[0])}
          {t.length > 1 && <span className="ml-1.5 font-mono text-[10.5px] text-fm-faint">+{t.length - 1}</span>}
        </span>
      );
    },
  },
  {
    id: "clauses",
    accessorFn: (c) => (c.clauses ?? []).join(" "),
    header: "Clauses",
    enableSorting: false,
    cell: ({ row }) => (
      <div className="flex gap-1">
        {(row.original.clauses ?? []).map((cl) => <Tag key={cl} tone="hold">§{cl}</Tag>)}
      </div>
    ),
  },
  {
    id: "verdict",
    accessorFn: (c) => c.verdict ?? "",
    header: "Verdict",
    cell: ({ row }) => <StatusBadge verdict={row.original.verdict} />,
  },
  {
    id: "held",
    accessorFn: (c) => c.held_paise,
    header: "Held",
    meta: { align: "right" },
    cell: ({ row }) => <Money paise={row.original.held_paise} className={row.original.held_paise > 0 ? "font-medium text-fm-hold" : undefined} />,
  },
  {
    id: "decided",
    accessorFn: (c) => c.decided_at ?? "",
    header: "Decided",
    cell: ({ row }) => (row.original.decided_at ? <span className="font-mono text-[11.5px] text-fm-muted">{formatTs(row.original.decided_at)}</span> : <span className="font-mono text-fm-faint">—</span>),
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
    <div className="mx-auto max-w-[1280px]">
      <PageHeader
        eyebrow="Ledger"
        title="Cases"
        meta={isLoading ? <Skeleton className="h-3.5 w-48" /> : (
          <>
            <span><span className="font-mono tabular-nums text-fm-text">{rows.length}</span> payment decisions</span>
            <span><span className="font-mono tabular-nums text-fm-hold">{kpi.heldCases}</span> on hold or partial</span>
            <span><span className="font-mono tabular-nums text-fm-text">{filtered.length}</span> shown</span>
          </>
        )}
      />

      <KpiStrip className="mb-4 md:grid-cols-4">
        <KpiTile label="Total held" tone="hold" value={isLoading ? "—" : formatINR(kpi.held)} hint="payment withheld across cases" />
        <KpiTile label="On hold or partial" value={isLoading ? "—" : kpi.heldCases} unit={`of ${rows.length}`} hint="payment not released in full" />
        <KpiTile label="Verified" tone="verified" value={isLoading ? "—" : kpi.verified} unit={`of ${rows.length}`} hint="documents and dock agree" />
        <KpiTile label="Video / documents only" value={isLoading ? "—" : `${kpi.video} / ${kpi.docs}`} hint="evidence source per case" />
      </KpiStrip>

      <Panel padded={false} bodyClassName="flex flex-col">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-fm-border px-3 py-2">
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
              { value: "all", label: "All" },
              { value: "video", label: "Video", count: kpi.video },
              { value: "document", label: "Documents", count: kpi.docs },
            ]}
          />
          <label className="relative ml-auto flex w-full items-center sm:w-64">
            <Search size={13} className="pointer-events-none absolute left-2 text-fm-faint" aria-hidden />
            <span className="sr-only">Filter by PO, vendor or clause</span>
            <input
              type="search"
              value={q}
              onChange={(e) => setParam("q", e.target.value, "")}
              placeholder="PO, vendor, clause"
              className="h-7 w-full rounded-fm-sm border border-fm-border-strong bg-fm-sunken pl-7 pr-2 text-[12.5px] text-fm-text placeholder:text-fm-faint focus:border-fm-hold focus:outline-none"
            />
          </label>
        </div>

        {isLoading ? (
          <SkeletonRows rows={7} className="p-3" />
        ) : isError ? (
          <ErrorState message={error instanceof Error ? error.message : "Could not load cases."} action={<button type="button" className="text-[12px] text-fm-hold underline" onClick={() => void refetch()}>Retry</button>} />
        ) : rows.length === 0 ? (
          <EmptyState title="No cases yet" description="Cases appear once a delivery has been checked against its PO." />
        ) : (
          <DataTable
            label="Cases"
            columns={columns}
            data={filtered}
            keyboard
            initialSorting={[{ id: "held", desc: true }]}
            emptyMessage={filtersActive ? "No cases match these filters." : "No cases"}
            onRowClick={(c) => navigate(`/cases/${c.po_id}`)}
          />
        )}

        <div className="flex items-center gap-1.5 border-t border-fm-border px-3 py-1.5 text-[11.5px] text-fm-faint">
          <Kbd>j</Kbd> / <Kbd>k</Kbd> to move <span aria-hidden>·</span> <Kbd>Enter</Kbd> to open
          {filtersActive && (
            <button type="button" className="ml-auto text-fm-muted hover:text-fm-text" onClick={() => setParams({}, { replace: true })}>
              Clear filters
            </button>
          )}
        </div>
      </Panel>
    </div>
  );
}
