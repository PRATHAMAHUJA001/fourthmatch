/** Cases list. Design + contract traceability: docs/CASES.md. */
import { useQuery } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { DataTable } from "../components/ui/DataTable";
import { EmptyState } from "../components/ui/EmptyState";
import { SkeletonRows } from "../components/ui/EmptyState";
import { KpiTile } from "../components/ui/KpiTile";
import { Money } from "../components/ui/Money";
import { StatusBadge } from "../components/ui/StatusBadge";
import { getCases } from "../lib/api";
import { formatINR } from "../lib/format";
import type { CaseSummary } from "../types/api";

const columns: ColumnDef<CaseSummary, unknown>[] = [
  {
    accessorKey: "po_number",
    header: "Purchase order",
    cell: ({ row }) => (
      <div>
        <div className="font-mono font-medium">{row.original.po_number}</div>
        {row.original.scenario_id && (
          <div className="text-[11px] text-fm-faint">{row.original.scenario_id}</div>
        )}
      </div>
    ),
  },
  { accessorKey: "vendor_name", header: "Vendor" },
  {
    accessorKey: "expected_date",
    header: "Expected",
    cell: ({ row }) => <span className="font-mono tabular-nums">{row.original.expected_date}</span>,
  },
  {
    accessorKey: "total_paise",
    header: "PO total",
    cell: ({ row }) => <Money paise={row.original.total_paise} />,
  },
  {
    accessorKey: "verdict",
    header: "Verdict",
    cell: ({ row }) =>
      row.original.verdict ? (
        <StatusBadge verdict={row.original.verdict} />
      ) : (
        <span className="text-[11px] font-semibold uppercase tracking-[0.04em] text-fm-muted">
          Not decided
        </span>
      ),
  },
  {
    accessorKey: "at_risk_paise",
    header: "At risk",
    cell: ({ row }) => <Money paise={row.original.at_risk_paise} />,
  },
  {
    accessorKey: "held_paise",
    header: "Held",
    cell: ({ row }) => <Money paise={row.original.held_paise} />,
  },
  {
    id: "lines",
    header: "Lines",
    cell: ({ row }) => (
      <span className="font-mono tabular-nums">
        {row.original.lines_evaluated}/{row.original.lines_total} evaluated
      </span>
    ),
  },
];

export function Cases() {
  const navigate = useNavigate();
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["cases"],
    queryFn: getCases,
  });

  const totals = useMemo(() => {
    const rows = data ?? [];
    return {
      count: rows.length,
      atRisk: rows.reduce((sum, c) => sum + c.at_risk_paise, 0),
      held: rows.reduce((sum, c) => sum + c.held_paise, 0),
      attention: rows.filter((c) => c.verdict !== null && c.verdict !== "approve").length,
      undecided: rows.filter((c) => c.verdict === null).length,
    };
  }, [data]);

  return (
    <div className="mx-auto max-w-6xl">
      <h1 className="text-[20px] font-semibold tracking-tight">Cases</h1>
      <p className="mt-0.5 text-[12px] text-fm-muted">
        PO · GRN · invoice vs. video — every hold with its policy clause. All numbers computed in Python.
      </p>

      <div className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KpiTile label="Cases" value={totals.count} hint="purchase orders" />
        <KpiTile label="Amount at risk" value={formatINR(totals.atRisk)} tone="hold" hint="genuinely disputed value" />
        <KpiTile label="Payment held" value={formatINR(totals.held)} tone="fraud" hint="cash withheld" />
        <KpiTile
          label="Needs attention"
          value={totals.attention}
          tone="review"
          hint={totals.undecided ? `${totals.undecided} not yet decided` : "held, partial or review"}
        />
      </div>

      <div className="mt-4">
        {isLoading ? (
          <SkeletonRows rows={5} />
        ) : isError ? (
          <div className="rounded-fm border border-fm-border bg-fm-panel">
            <EmptyState
              title="Could not load cases"
              description={error instanceof Error ? error.message : "Unknown error"}
            />
          </div>
        ) : (
          <DataTable
            columns={columns}
            data={data ?? []}
            emptyMessage="No cases yet"
            onRowClick={(row) => navigate(`/cases/${row.po_id}`)}
          />
        )}
      </div>
    </div>
  );
}
