import { useQuery } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { DataTable } from "../components/ui/DataTable";
import { ErrorState, Skeleton } from "../components/ui/EmptyState";
import { KpiStrip, KpiTile } from "../components/ui/KpiTile";
import { PageHeader, Panel } from "../components/ui/Panel";
import { StatusBadge } from "../components/ui/StatusBadge";
import { api } from "../lib/api";
import { IS_MOCK } from "../lib/demo";
import { VERDICT_LABEL, type EvalCountRow, type EvalRead } from "../types/api";
import { ConfusionMatrix } from "./eval/Confusion";
import { CountBars } from "./eval/CountBars";
import { AgentPanel, CostPanel, ImageEvalPanel, NotMeasured, pctOrDash } from "./eval/Sections";

type Metric = EvalRead["verdict_metrics"][number];
type Latency = EvalRead["latency"][number];

const num = "font-mono tabular-nums";
const dec = (v: number | null) => (v === null ? <span className="font-mono text-fm-faint">—</span> : <span className={num}>{v.toFixed(2)}</span>);
const ms = (v: number | null) => (v === null ? <span className="font-mono text-fm-faint">—</span> : <span className={num}>{Math.round(v)} ms</span>);
const pct = (v: number) => (v * 100).toFixed(1);

const metricCols: ColumnDef<Metric, unknown>[] = [
  { accessorKey: "label", header: "Verdict", cell: (i) => <StatusBadge verdict={i.getValue<Metric["label"]>()} label={VERDICT_LABEL[i.getValue<Metric["label"]>()]} size="sm" /> },
  { accessorKey: "precision", header: "Precision", meta: { align: "right" }, cell: (i) => dec(i.getValue<number | null>()) },
  { accessorKey: "recall", header: "Recall", meta: { align: "right" }, cell: (i) => dec(i.getValue<number | null>()) },
  { accessorKey: "f1", header: "F1", meta: { align: "right" }, cell: (i) => dec(i.getValue<number | null>()) },
  { accessorKey: "support", header: "Support", meta: { align: "right" }, cell: (i) => <span className={num}>{i.getValue<number>()}</span> },
];

const countCols: ColumnDef<EvalCountRow, unknown>[] = [
  { accessorKey: "scenario", header: "Scenario", cell: (i) => <span className="font-mono">{i.getValue<string>()}</span> },
  { accessorKey: "category", header: "Category", cell: (i) => <span className="text-fm-muted">{i.getValue<string>().replaceAll("_", " ")}</span> },
  { accessorKey: "noun_phrase", header: "SAM noun phrase", cell: (i) => <span>“{i.getValue<string>()}”</span> },
  { accessorKey: "true_count", header: "True", meta: { align: "right" }, cell: (i) => <span className={num}>{i.getValue<number>()}</span> },
  { accessorKey: "observed_count", header: "Observed", meta: { align: "right" }, cell: (i) => <span className={num}>{i.getValue<number>()}</span> },
  { accessorKey: "max_visible", header: "Max visible", meta: { align: "right" }, cell: (i) => <span className={`${num} text-fm-muted`}>{i.getValue<number>()}</span> },
  { accessorKey: "evidence_quality", header: "Quality", cell: (i) => <StatusBadge quality={i.getValue<EvalCountRow["evidence_quality"]>()} size="sm" /> },
  { id: "damage", header: "Damage true / flagged", meta: { align: "right" }, enableSorting: false, cell: ({ row }) => <span className={num}>{row.original.true_damaged} / {row.original.flagged_damaged}</span> },
  {
    accessorKey: "result", header: "Result",
    cell: (i) => (i.getValue<string>() === "PASS" ? <StatusBadge signal="verified" label="PASS" size="sm" /> : <StatusBadge signal="fraud" label="FAIL" size="sm" />),
  },
];

const latencyCols: ColumnDef<Latency, unknown>[] = [
  { accessorKey: "model", header: "Model", cell: (i) => <span className="font-mono text-[13px]">{i.getValue<string>()}</span> },
  { accessorKey: "role", header: "Role", cell: (i) => <span className="text-fm-muted">{i.getValue<string>()}</span> },
  { accessorKey: "calls", header: "Calls", meta: { align: "right" }, cell: (i) => <span className={num}>{i.getValue<number>()}</span> },
  { accessorKey: "p50_ms", header: "p50", meta: { align: "right" }, cell: (i) => ms(i.getValue<number | null>()) },
  { accessorKey: "p95_ms", header: "p95", meta: { align: "right" }, cell: (i) => ms(i.getValue<number | null>()) },
];

export function Eval() {
  const q = useQuery({ queryKey: ["eval"], queryFn: api.eval });
  const header = (
    <PageHeader
      eyebrow="Evaluation against ground truth"
      title="How often is it right?"
      meta={<span>Counts come only from SAM 3.1 tracks merged in Python. The model never counts.</span>}
    />
  );

  if (q.isError) return <div>{header}<Panel><ErrorState message={q.error.message} /></Panel></div>;
  if (!q.data) {
    return (
      <div>
        {header}
        <Skeleton className="mb-6 h-[148px] w-full rounded-fm" />
        <div className="grid gap-6 lg:grid-cols-2"><Skeleton className="h-[280px] rounded-fm" /><Skeleton className="h-[280px] rounded-fm" /></div>
      </div>
    );
  }

  const d = q.data;
  const pass = d.counts.filter((c) => c.result === "PASS").length;
  const res = d.results;
  const imgSummary = res?.images.summary ?? null;
  const imgHint = res && res.images.images_total > 0
    ? `synthetic · ${res.images.images_confirmed}/${res.images.images_total} confirmed`
    : "synthetic · none confirmed yet";
  const macro = res?.verdicts.served ?? null;
  const noLatency = d.latency.every((l) => l.p50_ms === null && l.p95_ms === null);

  return (
    <div>
      {header}
      <KpiStrip className="mb-6 grid-cols-2 lg:grid-cols-5 max-lg:divide-x max-md:[&>*:nth-child(odd)]:border-l-0">
        <KpiTile label="Verdict accuracy" tone={IS_MOCK ? "neutral" : "verified"} value={IS_MOCK ? "—" : pct(d.verdict_accuracy)} unit={IS_MOCK ? undefined : "%"} hint={IS_MOCK ? "Measured on the live agent run" : "Served verdict vs ground truth"} />
        <KpiTile label="Video count accuracy" tone="verified" value={pct(d.count_accuracy)} unit="%" hint="SAM tracks vs manifest" />
        <KpiTile label="Image count accuracy" value={pctOrDash(imgSummary?.accuracy)} unit={imgSummary?.accuracy == null ? undefined : "%"} hint={imgHint} />
        <KpiTile label="Cases evaluated" value={d.cases_total} hint="Synthetic scenarios" />
        <KpiTile label="Video lines passing" tone={pass === d.counts.length ? "verified" : "hold"} value={<>{pass}<span className="text-fm-faint"> / {d.counts.length}</span></>} hint="Count within manifest" />
      </KpiStrip>
      {IS_MOCK && (
        <p className="mb-6 rounded-fm bg-fm-panel px-6 py-4 text-[14px] leading-relaxed text-fm-muted">
          <span className="font-semibold text-fm-text">Demo replay. </span>
          Count rows are the real SAM 3.1 run in <span className="font-mono text-[13px]">data/eval_counts.json</span>. Verdicts are replayed from ground truth until the decision agent runs live, so verdict accuracy here is not yet a measurement.
        </p>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
        <Panel title="Verdict metrics" subtitle="Per label, served verdicts" padded={false} bodyClassName="px-2 pb-2">
          <DataTable<Metric> columns={metricCols} data={d.verdict_metrics} label="Verdict metrics" />
          <p className="border-t border-fm-border px-4 pt-3 text-[13px] text-fm-muted">
            Macro precision <span className="font-mono">{macro?.macro_precision == null ? "—" : macro.macro_precision.toFixed(2)}</span>, recall <span className="font-mono">{macro?.macro_recall == null ? "—" : macro.macro_recall.toFixed(2)}</span>, F1 <span className="font-mono">{macro?.macro_f1 == null ? "—" : macro.macro_f1.toFixed(2)}</span>
            {macro ? "." : " (served verdicts not measured in the eval report)."}
          </p>
          <p className="px-4 pb-3 pt-2 text-[12px] text-fm-faint">
            Precision is correct holds of this kind over all predicted; recall is caught over all in ground truth. A label with zero support shows “—” because the ratio is undefined, not zero.
          </p>
        </Panel>
        <Panel title="Confusion matrix" subtitle="Rows are ground truth, columns the agent"><ConfusionMatrix data={d.confusion} /></Panel>
      </div>

      <Panel title="Count accuracy per video" subtitle="True count vs SAM-observed count" padded={false} className="mt-6" bodyClassName="px-2 pb-2">
        <CountBars rows={d.counts} />
        <DataTable<EvalCountRow> columns={countCols} data={d.counts} label="Count accuracy per video" />
      </Panel>

      <ImageEvalPanel results={res} />

      <Panel title="Model latency" subtitle="p50 / p95 over live calls" padded={false} className="mt-6" bodyClassName="px-2 pb-2">
        <DataTable<Latency> columns={latencyCols} data={d.latency} label="Model latency" />
        {noLatency && <p className="border-t border-fm-border px-4 py-3 text-[13px] text-fm-muted">Latency fills in from the model_calls table when the backend runs live.</p>}
      </Panel>

      <CostPanel results={res} />
      <AgentPanel results={res} />
      <NotMeasured results={res} />
    </div>
  );
}
