/** Delivery Case: the hero screen. Video evidence left, the four-way match + decision right. */
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Download, FileWarning, ShieldCheck, Undo2, Hand } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { AgentTrace } from "../components/evidence/AgentTrace";
import { EvidenceSeal } from "../components/evidence/EvidenceSeal";
import { EvidenceVideo, type EvidenceVideoHandle } from "../components/evidence/EvidenceVideo";
import { Filmstrip } from "../components/evidence/Filmstrip";
import { Button } from "../components/ui/Button";
import { EmptyState, ErrorState, Skeleton } from "../components/ui/EmptyState";
import { FourMatchStrip } from "../components/ui/FourMatch";
import { LoadDiagram } from "../components/ui/LoadDiagram";
import { Money, Qty } from "../components/ui/Money";
import { Panel } from "../components/ui/Panel";
import { StatusBadge, VERDICT_SIGNAL } from "../components/ui/StatusBadge";
import { SignalGlyph } from "../components/ui/Glyph";
import { Tag } from "../components/ui/Tag";
import { api } from "../lib/api";
import { cn } from "../lib/cn";
import { IS_MOCK } from "../lib/demo";
import { formatDate, formatINR, formatTs, titleCase } from "../lib/format";
import type { CaseDetail as CaseDetailT, CaseLineRead, CitedRule } from "../types/api";
import { VERDICT_LABEL } from "../types/api";

function downloadPack(c: CaseDetailT) {
  const blob = new Blob([JSON.stringify({
    kind: "fourthmatch.evidence_pack", synthetic: true, po_number: c.po_number, vendor: c.vendor_name,
    verdict: c.verdict, held_paise: c.held_paise, lines: c.lines, decision: c.decision, evidence_pack: c.evidence_pack,
  }, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `${c.po_number.replaceAll("/", "-")}_evidence_pack.json`;
  a.click();
  URL.revokeObjectURL(a.href);
}

function LineStrip({ line, highlight }: { line: CaseLineRead; highlight?: boolean }) {
  const contradicted = line.evidence_source === "video" && line.observed_count !== null && line.grn_qty !== null && line.observed_count !== line.grn_qty;
  return (
    <div className={cn("rounded-fm border border-transparent p-0", highlight && "")}>
      <div className="mb-2 flex items-baseline justify-between gap-2">
        <div className="flex min-w-0 items-baseline gap-2">
          <span className="font-mono text-[10.5px] text-fm-faint">L{line.line_no}</span>
          <span className="font-mono text-[12.5px] font-medium">{line.sku}</span>
          <span className="truncate text-[12px] text-fm-muted">{line.description}</span>
        </div>
        {line.verdict && <StatusBadge verdict={line.verdict} size="sm" />}
      </div>
      <FourMatchStrip
        values={{ po: line.po_qty, grn: line.grn_qty, invoice: line.invoiced_qty, vision: line.evidence_source === "video" ? line.observed_count : null }}
        unit={line.unit}
        variancePct={line.variance_pct}
        sub={{
          po: <span className="font-mono">{formatINR(line.po_unit_price_paise)}/{line.unit}</span>,
          grn: contradicted ? <span className="text-fm-hold">contradicted · §8.4</span> : "storekeeper signed",
          invoice: line.unit_price_paise !== line.po_unit_price_paise
            ? <span className="font-mono text-fm-hold">{formatINR(line.unit_price_paise)}/{line.unit}</span>
            : <span className="font-mono">{formatINR(line.unit_price_paise)}/{line.unit}</span>,
          vision: line.evidence_source === "video"
            ? <span className="font-mono">{line.perception?.observed_count ?? "—"} SAM tracks</span>
            : "no dock video",
        }}
      />
      {line.evidence_source === "video" && line.observed_count !== null && (
        <div className="mt-3 flex items-center gap-4 rounded-fm border border-fm-border bg-fm-sunken px-3 py-2">
          <LoadDiagram className="max-w-[260px]" invoiced={line.invoiced_qty} observed={line.observed_count} damaged={line.damage_count} unit={line.unit} />
          <dl className="grid shrink-0 grid-cols-[auto_auto] gap-x-3 gap-y-0.5 font-mono text-[11px]">
            <dt className="text-fm-faint">billed</dt><dd className="text-right">{line.invoiced_qty}</dd>
            <dt className="text-fm-faint">seen</dt><dd className="text-right">{line.observed_count}</dd>
            {line.invoiced_qty - line.observed_count > 0 && (<><dt className="text-fm-hold">missing</dt><dd className="text-right text-fm-hold">{line.invoiced_qty - line.observed_count}</dd></>)}
            {line.damage_count > 0 && (<><dt className="text-fm-hold">damaged</dt><dd className="text-right text-fm-hold">{line.damage_count}</dd></>)}
          </dl>
        </div>
      )}
      {(line.damage_count > 0 || line.evidence_quality === "insufficient") && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {line.damage_count > 0 && <Tag tone="hold">{line.damage_count} damaged · track {line.perception?.damaged_track_ids.join(", ") ?? "GRN"}</Tag>}
          {line.evidence_quality === "insufficient" && <StatusBadge quality="insufficient" size="sm" />}
        </div>
      )}
    </div>
  );
}

function ClauseQuote({ rule }: { rule: CitedRule }) {
  return (
    <figure className="border-l-2 border-fm-hold pl-3">
      <figcaption className="mb-1 flex items-center gap-2">
        <Tag tone="hold">§{rule.source_clause}</Tag>
        <Link to={`/policy?clause=${rule.source_clause}`} className="font-mono text-[11px] text-fm-muted hover:text-fm-text">{rule.rule_id}</Link>
        <span className="font-cond text-[10px] font-semibold uppercase tracking-[0.08em] text-fm-faint">→ {titleCase(rule.action)}</span>
      </figcaption>
      <blockquote className="text-[12.5px] leading-relaxed text-fm-muted">
        “{rule.source_text}”
      </blockquote>
    </figure>
  );
}

export function CaseDetail() {
  const { poId } = useParams();
  const id = Number(poId);
  const player = useRef<EvidenceVideoHandle>(null);
  const [action, setAction] = useState<string | null>(null);
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["case", id],
    queryFn: () => api.case(id),
    enabled: Number.isFinite(id),
  });

  const citedRules = useMemo(() => {
    const byId = new Map<string, CitedRule>();
    for (const line of data?.lines ?? []) for (const rule of line.cited_rules) byId.set(rule.rule_id, rule);
    return [...byId.values()];
  }, [data]);

  if (isLoading) {
    return (
      <div className="flex flex-col gap-4" role="status" aria-label="Loading case">
        <Skeleton className="h-10 w-80" />
        <Skeleton className="h-28 w-full" />
        <div className="grid gap-4 lg:grid-cols-[1.45fr_1fr]"><Skeleton className="aspect-video w-full" /><Skeleton className="h-96 w-full" /></div>
      </div>
    );
  }
  if (isError || !data) {
    return (
      <div className="rounded-fm border border-fm-border bg-fm-panel">
        <ErrorState message={error instanceof Error ? error.message : "This purchase order does not exist."} action={<Button asChild size="sm"><Link to="/cases">Back to cases</Link></Button>} />
      </div>
    );
  }

  const videoLine = data.lines.find((l) => l.perception);
  const totalObserved = data.lines.reduce((s, l) => s + (l.perception?.observed_count ?? 0), 0);
  const verdict = data.verdict;
  const evidenceTracks = data.lines.flatMap((l) => (l.perception?.track_ids ?? []).map((t) => ({ t, line: l, damaged: l.perception?.damaged_track_ids.includes(t) ?? false })));

  return (
    <div className="flex flex-col gap-4">
      {/* ——— header ——— */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <Link to="/cases" className="mb-1.5 inline-flex items-center gap-1 text-[12px] text-fm-muted hover:text-fm-text">
            <ArrowLeft size={13} /> Cases
          </Link>
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="font-mono text-[22px] font-medium tracking-[-0.02em]">{data.po_number}</h1>
            <StatusBadge verdict={verdict} size="md" />
            {data.scenario_id && <Tag>{data.scenario_id}</Tag>}
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-fm-muted">
            <span className="text-fm-text">{data.vendor_name}</span>
            {data.grn_number && <span className="font-mono">{data.grn_number}</span>}
            {data.invoice_number && <span className="font-mono">Inv {data.invoice_number}</span>}
            <span className="font-mono">Expected {formatDate(data.expected_date)}</span>
            {data.policy_version && <span className="font-mono">Policy v{data.policy_version}</span>}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <Button size="sm" variant="ghost" onClick={() => setAction("Override requires joint sign-off by the Purchase Manager and Finance Controller (§3.6). Request sent.")}><Undo2 size={13} /> Approve override</Button>
          <Button size="sm" variant="hold" onClick={() => setAction("Full hold placed. Purchase and supplier notified within 3 working days (§7.2).")}><Hand size={13} /> Hold</Button>
          {verdict === "partial_pay" && (
            <Button size="sm" variant="secondary" onClick={() => setAction(`Debit note drafted for ${formatINR(data.held_paise)}. Issue within 7 working days (§6.3).`)}><FileWarning size={13} /> Issue debit note</Button>
          )}
          <Button size="sm" variant="primary" onClick={() => (IS_MOCK || !data.delivery_id ? downloadPack(data) : window.open(`/api/deliveries/${data.delivery_id}/evidence-pack`))}>
            <Download size={13} /> Evidence pack
          </Button>
        </div>
      </div>
      {action && (
        <div className="fm-rise flex items-center justify-between gap-3 rounded-fm border border-fm-border-strong bg-fm-raised px-3 py-2 text-[12.5px]" role="status">
          <span className="flex items-center gap-2"><ShieldCheck size={14} className="text-fm-verified" />{action}</span>
          <button type="button" className="font-mono text-[11px] text-fm-faint hover:text-fm-text" onClick={() => setAction(null)}>dismiss</button>
        </div>
      )}

      {/* ——— verdict band ——— */}
      {verdict && (() => {
        const ok = verdict === "approve";
        const sub = ok ? "text-fm-muted" : "opacity-75";
        const amount = ok ? data.invoice_total_paise ?? data.total_paise : data.held_paise;
        return (
          <section
            className={cn(
              "grid overflow-hidden rounded-fm border md:grid-cols-[minmax(0,1fr)_auto]",
              ok ? "border-fm-verified-line bg-fm-verified-bg" : "fm-amber-block border-transparent",
            )}
            aria-label="Verdict"
          >
            <div className="flex min-w-0 flex-col justify-center gap-3 px-6 py-6">
              <span className={cn("font-cond text-[11px] font-semibold uppercase tracking-[0.1em]", sub)}>Verdict</span>
              <span className={cn("flex items-center gap-3 font-cond text-[44px] font-bold uppercase leading-none tracking-[0.01em]", ok && "text-fm-verified")}>
                <SignalGlyph signal={VERDICT_SIGNAL[verdict]} size={34} />
                {VERDICT_LABEL[verdict]}
              </span>
              <p className="max-w-3xl text-[15px] leading-relaxed">{data.decision?.summary_en ?? "Decision pending."}</p>
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[12.5px]">
                {data.decision && (
                  <span className="flex items-center gap-2"><span className={cn("font-cond text-[11px] font-semibold uppercase tracking-[0.1em]", sub)}>Next</span>{data.decision.recommended_action}</span>
                )}
                {(data.clauses ?? []).map((cl) => (
                  <span key={cl} className={cn("inline-flex h-5 items-center rounded-fm-sm border px-1.5 font-mono text-[10.5px] font-medium", ok ? "border-fm-verified-line text-fm-verified" : "border-black/35")}>§{cl}</span>
                ))}
              </div>
            </div>
            <div className={cn("flex flex-col justify-center gap-1.5 border-t px-6 py-6 md:min-w-[340px] md:border-l md:border-t-0 md:text-right", ok ? "border-fm-verified-line" : "border-black/15")}>
              <span className={cn("font-cond text-[11px] font-semibold uppercase tracking-[0.1em]", sub)}>{ok ? "Payable" : "Held"}</span>
              <span className={cn("font-mono text-[56px] font-medium leading-none tracking-[-0.05em] tabular-nums max-sm:text-[40px]", ok && "text-fm-verified")}>
                {formatINR(amount)}
              </span>
              {data.invoice_total_paise != null && !ok && (
                <span className={cn("font-mono text-[11.5px]", sub)}>of {formatINR(data.invoice_total_paise)} invoiced (incl. GST)</span>
              )}
              {data.decided_at && <span className={cn("font-mono text-[11px]", sub)}>{formatTs(data.decided_at)} IST</span>}
            </div>
          </section>
        );
      })()}

      {/* ——— main grid ——— */}
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <div className="flex min-w-0 flex-col gap-4">
          {data.video_url ? (
            <Panel
              index="01"
              title="Dock evidence"
              subtitle={videoLine?.perception ? `${totalObserved} unique tracks · max ${data.lines.reduce((m, l) => m + (l.perception?.max_visible ?? 0), 0)} visible in one frame` : undefined}
              actions={<Tag tone="info">muse-spark-1.3 → sam-3.1</Tag>}
              padded={false}
            >
              <div className="p-3">
                <EvidenceVideo
                  ref={player}
                  src={data.video_url}
                  phrase={data.lines.map((l) => l.perception?.noun_phrase).filter(Boolean).join(" + ")}
                  count={totalObserved}
                  countLabel="Unique tracks"
                />
              </div>
              <div className="border-t border-fm-border px-3 py-2.5">
                <div className="mb-2 flex items-center justify-between">
                  <span className="fm-label">Evidence frames</span>
                  <span className="font-mono text-[10.5px] text-fm-faint">click to seek</span>
                </div>
                <Filmstrip src={data.video_url} onSelect={(t) => player.current?.seek(t)} />
              </div>
              <div className="border-t border-fm-border px-3 py-2.5">
                <div className="mb-2 flex items-center justify-between">
                  <span className="fm-label">Track roster</span>
                  <span className="font-mono text-[10.5px] text-fm-faint">score ≥ 0.80 · merged in Python</span>
                </div>
                <div className="flex flex-wrap gap-1">
                  {evidenceTracks.map(({ t, line, damaged }) => (
                    <span
                      key={`${line.po_line_id}-${t}`}
                      title={`${line.perception?.noun_phrase} · track ${t}${damaged ? " · damaged" : ""}`}
                      className={cn("inline-flex h-6 items-center gap-1 rounded-[3px] border px-1.5 font-mono text-[10.5px]",
                        damaged ? "border-fm-hold bg-fm-hold-bg text-fm-hold" : "border-fm-border bg-fm-raised text-fm-muted")}
                    >
                      {damaged && <SignalGlyph signal="fraud" size={9} />}
                      {data.lines.length > 1 ? `L${line.line_no}·` : ""}T{t.padStart(2, "0")}
                    </span>
                  ))}
                </div>
              </div>
            </Panel>
          ) : (
            <Panel index="01" title="Dock evidence" padded={false}>
              <EmptyState
                title="Documents only"
                description="No dock video exists for this delivery. The GRN count is the only receiving evidence, so the decision rests on document checks."
              />
            </Panel>
          )}

          <Panel index="03" title="Agent trace" subtitle={data.decision ? `${data.decision.trace.length} tool calls · ${data.decision.model} · reasoning high` : undefined}>
            {data.decision ? <AgentTrace steps={data.decision.trace} /> : <p className="text-[12px] text-fm-muted">No decision recorded yet.</p>}
          </Panel>
        </div>

        <div className="flex min-w-0 flex-col gap-4">
          <Panel index="02" title="The fourth match" subtitle="PO · GRN · Invoice · Vision" ticks>
            <div className="flex flex-col gap-5">
              {data.lines.map((l) => <LineStrip key={l.po_line_id} line={l} />)}
            </div>
          </Panel>

          <Panel index="04" title="Policy cited" subtitle={citedRules.length ? `${citedRules.length} rule${citedRules.length > 1 ? "s" : ""} fired` : "no rule fired"}>
            {citedRules.length ? (
              <div className="flex flex-col gap-4">{citedRules.map((r) => <ClauseQuote key={r.rule_id} rule={r} />)}</div>
            ) : (
              <p className="text-[12.5px] text-fm-muted">All four sources agree within tolerance. No clause blocks payment.</p>
            )}
          </Panel>

          <Panel index="05" title="Ledger impact">
            <table className="w-full text-[12.5px]">
              <thead>
                <tr className="fm-label text-left">
                  <th className="pb-1.5 font-semibold">Line</th>
                  <th className="pb-1.5 text-right font-semibold">Value</th>
                  <th className="pb-1.5 text-right font-semibold">At risk</th>
                  <th className="pb-1.5 text-right font-semibold">Held</th>
                </tr>
              </thead>
              <tbody>
                {data.lines.map((l) => (
                  <tr key={l.po_line_id} className="border-t border-fm-border">
                    <td className="py-1.5"><span className="font-mono">{l.sku}</span> <Qty value={l.invoiced_qty} unit={l.unit} className="ml-1 text-fm-muted" /></td>
                    <td className="py-1.5 text-right"><Money paise={l.line_value_paise} /></td>
                    <td className="py-1.5 text-right"><Money paise={l.at_risk_paise} /></td>
                    <td className="py-1.5 text-right"><Money paise={l.held_paise} className={l.held_paise > 0 ? "text-fm-hold" : undefined} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-2 text-[11px] text-fm-faint">Ex-GST. Every rupee recomputed in Python after the agent records its decision.</p>
          </Panel>

          {data.evidence_pack && <EvidenceSeal pack={data.evidence_pack} />}
        </div>
      </div>
    </div>
  );
}
