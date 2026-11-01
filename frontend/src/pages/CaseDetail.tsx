import { useQuery } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { ArrowLeft, FileText } from "lucide-react";
import { useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Button } from "../components/ui/Button";
import { DataTable } from "../components/ui/DataTable";
import { EmptyState, SkeletonRows } from "../components/ui/EmptyState";
import { KpiTile } from "../components/ui/KpiTile";
import { Money, Qty } from "../components/ui/Money";
import { Panel } from "../components/ui/Panel";
import { StatusBadge } from "../components/ui/StatusBadge";
import { getCase } from "../lib/api";
import { formatINR, formatPct } from "../lib/format";
import type { CaseLineRead, CitedRule } from "../types/api";

function fmtQty(value: number | null): string {
  return value === null ? "—" : String(value);
}

function varianceText(line: CaseLineRead): string {
  if (line.variance_pct === null) return "—";
  return formatPct(line.variance_pct);
}

const lineColumns: ColumnDef<CaseLineRead, unknown>[] = [
  {
    id: "line",
    header: "Line",
    cell: ({ row }) => (
      <div>
        <div className="font-mono font-medium">{row.original.sku}</div>
        <div className="max-w-[220px] truncate text-[11px] text-fm-faint">{row.original.description}</div>
      </div>
    ),
  },
  { id: "po", header: "PO qty", cell: ({ row }) => <Qty value={row.original.po_qty} unit={row.original.unit} /> },
  { id: "grn", header: "GRN qty", cell: ({ row }) => fmtQty(row.original.grn_qty) },
  { id: "inv", header: "Invoiced", cell: ({ row }) => <Qty value={row.original.invoiced_qty} /> },
  {
    id: "observed",
    header: "Observed",
    cell: ({ row }) => (
      <div>
        <div className="font-mono tabular-nums font-semibold">{fmtQty(row.original.observed_count)}</div>
        <div className="text-[11px] text-fm-faint">
          {row.original.evidence_source === "video"
            ? "SAM tracks"
            : row.original.evidence_source === "document"
              ? "GRN document"
              : "no evidence"}
        </div>
      </div>
    ),
  },
  { id: "damage", header: "Damaged", cell: ({ row }) => <Qty value={row.original.damage_count} /> },
  {
    id: "variance",
    header: "Variance vs PO",
    cell: ({ row }) => <span className="font-mono tabular-nums">{varianceText(row.original)}</span>,
  },
  {
    id: "evidence",
    header: "Evidence",
    cell: ({ row }) =>
      row.original.evidence_quality ? (
        <StatusBadge quality={row.original.evidence_quality} />
      ) : (
        <span className="text-[11px] text-fm-muted">
          {row.original.evidence_source === "document" ? "Document" : "—"}
        </span>
      ),
  },
  {
    id: "verdict",
    header: "Verdict",
    cell: ({ row }) =>
      row.original.verdict ? (
        <StatusBadge verdict={row.original.verdict} />
      ) : (
        <span className="text-[11px] font-semibold uppercase tracking-[0.04em] text-fm-muted">Not decided</span>
      ),
  },
  { id: "at_risk", header: "At risk", cell: ({ row }) => <Money paise={row.original.at_risk_paise} /> },
];

export function CaseDetail() {
  const { poId } = useParams();
  const navigate = useNavigate();
  const id = Number(poId);
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["case", id],
    queryFn: () => getCase(id),
    enabled: Number.isFinite(id),
  });

  const citedRules = useMemo(() => {
    const byId = new Map<string, CitedRule>();
    for (const line of data?.lines ?? []) {
      for (const rule of line.cited_rules) byId.set(rule.rule_id, rule);
    }
    return [...byId.values()];
  }, [data]);

  if (isLoading) {
    return (
      <div className="mx-auto max-w-6xl">
        <SkeletonRows rows={6} />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="mx-auto max-w-6xl">
        <Button variant="ghost" size="sm" onClick={() => navigate("/cases")}>
          <ArrowLeft size={14} /> Back to cases
        </Button>
        <div className="mt-4 rounded-fm border border-fm-border bg-fm-panel">
          <EmptyState
            title="Case not found"
            description={error instanceof Error ? error.message : "This purchase order does not exist."}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl">
      <Button variant="ghost" size="sm" onClick={() => navigate("/cases")}>
        <ArrowLeft size={14} /> Back to cases
      </Button>

      <div className="mt-2 flex flex-wrap items-center gap-3">
        <h1 className="font-mono text-[20px] font-semibold tracking-tight">{data.po_number}</h1>
        {data.verdict ? (
          <StatusBadge verdict={data.verdict} />
        ) : (
          <span className="text-[11px] font-semibold uppercase tracking-[0.04em] text-fm-muted">Not decided</span>
        )}
      </div>
      <p className="mt-0.5 text-[12px] text-fm-muted">
        {data.vendor_name}
        {data.grn_number ? ` · ${data.grn_number}` : ""}
        {data.invoice_number ? ` · Invoice ${data.invoice_number}` : ""}
        {data.policy_version ? ` · Policy v${data.policy_version}` : ""}
        {data.scenario_id ? ` · ${data.scenario_id}` : ""}
      </p>

      <div className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KpiTile label="Amount at risk" value={formatINR(data.at_risk_paise)} tone="hold" />
        <KpiTile label="Payment held" value={formatINR(data.held_paise)} tone="fraud" />
        <KpiTile label="PO total" value={formatINR(data.total_paise)} />
        <KpiTile
          label="Lines evaluated"
          value={`${data.lines_evaluated}/${data.lines_total}`}
          tone="review"
          hint={data.signoff_roles.length ? `signoff: ${data.signoff_roles.join(", ")}` : undefined}
        />
      </div>

      <Panel title="PO vs GRN vs invoice vs observed" subtitle="Observed comes only from SAM tracks (video) or the GRN (document lines)" className="mt-4" padded={false}>
        <DataTable columns={lineColumns} data={data.lines} emptyMessage="No lines" />
      </Panel>

      <Panel title="Cited policy clauses" subtitle="Rules that triggered, resolved in Python from the approved policy" className="mt-4">
        {citedRules.length === 0 ? (
          <p className="text-[12px] text-fm-muted">
            No policy rule triggered for this case.
            {data.verdict === "human_review" ? " It is in human review because the evidence is insufficient — weak evidence is never a basis to approve." : ""}
          </p>
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {citedRules.map((rule) => (
              <div key={rule.rule_id} className="rounded-fm border border-fm-border bg-fm-raised p-3">
                <div className="flex items-center gap-2">
                  <FileText size={14} className="text-fm-muted" aria-hidden />
                  <span className="font-mono text-[12px] font-semibold">§{rule.source_clause}</span>
                  <span className="font-mono text-[11px] text-fm-faint">{rule.rule_id}</span>
                  <span className="ml-auto text-[11px] font-semibold uppercase tracking-[0.04em] text-fm-hold">
                    {rule.action.replace("_", " ")}
                  </span>
                </div>
                <p className="mt-2 text-[12px] leading-relaxed text-fm-muted">{rule.source_text}</p>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
