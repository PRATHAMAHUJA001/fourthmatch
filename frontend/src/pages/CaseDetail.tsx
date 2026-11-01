/** Delivery Case: the demo hero screen. A calm header, the verdict as one large card with the
 *  clauses it rests on, the four sources side by side, then the dock footage and its trail. */
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Download, FileWarning, Hand, ShieldCheck, Undo2, X } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { AgentTrace } from "../components/evidence/AgentTrace";
import { EvidenceSeal } from "../components/evidence/EvidenceSeal";
import { EvidenceVideo, type EvidenceVideoHandle } from "../components/evidence/EvidenceVideo";
import { Filmstrip } from "../components/evidence/Filmstrip";
import { RemarkNotSupportedChip, RemarkPanel } from "../components/evidence/RemarkPanel";
import { Button } from "../components/ui/Button";
import { EmptyState, ErrorState, Skeleton } from "../components/ui/EmptyState";
import { FourMatchStrip } from "../components/ui/FourMatch";
import { SignalGlyph } from "../components/ui/Glyph";
import { LoadDiagram } from "../components/ui/LoadDiagram";
import { Money, Qty } from "../components/ui/Money";
import { Panel } from "../components/ui/Panel";
import { StatusBadge, VERDICT_SIGNAL } from "../components/ui/StatusBadge";
import { api } from "../lib/api";
import { cn } from "../lib/cn";
import { IS_MOCK } from "../lib/demo";
import { formatDate, formatINR, formatTs, titleCase } from "../lib/format";
import type { CaseDetail as CaseDetailT, CaseLineRead, CitedRule, Verdict } from "../types/api";
import { VERDICT_LABEL } from "../types/api";
import { SCENARIO_FRAMES } from "../lib/media";

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

const TONE: Record<Verdict, { text: string; label: string }> = {
  approve: { text: "text-fm-verified", label: "Payable" },
  partial_pay: { text: "text-fm-hold", label: "Held" },
  hold: { text: "text-fm-hold", label: "Held" },
  human_review: { text: "text-fm-review", label: "Held for review" },
};

/* ——— verdict card ——— */

function ClauseQuote({ rule }: { rule: CitedRule }) {
  return (
    <figure className="min-w-0">
      <figcaption className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="fm-figure text-[28px] leading-none tracking-[-0.03em]">§{rule.source_clause}</span>
        <span className="text-[13px] font-semibold text-fm-muted">{titleCase(rule.action)}</span>
        <Link to={`/policy?clause=${rule.source_clause}`} className="ml-auto font-mono text-[12px] text-fm-faint hover:text-fm-accent-text">{rule.rule_id}</Link>
      </figcaption>
      <blockquote className="mt-3 text-[15px] leading-[1.6] text-fm-muted">“{rule.source_text}”</blockquote>
    </figure>
  );
}

function VerdictCard({ data, rules }: { data: CaseDetailT; rules: CitedRule[] }) {
  const verdict = data.verdict!;
  const ok = verdict === "approve";
  const tone = TONE[verdict];
  const amount = ok ? data.invoice_total_paise ?? data.total_paise : data.held_paise;
  return (
    <section className="rounded-fm-xl bg-fm-panel p-10 max-lg:p-8 max-sm:p-6" aria-label="Verdict">
      <div className="grid gap-x-12 gap-y-8 lg:grid-cols-[minmax(0,1fr)_auto]">
        <div className="min-w-0">
          <p className={cn("flex items-center gap-3 text-[40px] font-bold leading-none tracking-[-0.034em] max-sm:text-[32px]", tone.text)}>
            <SignalGlyph signal={VERDICT_SIGNAL[verdict]} size={30} className="shrink-0" />
            {VERDICT_LABEL[verdict]}
          </p>
          <p className="mt-6 max-w-[56ch] text-[21px] font-medium leading-[1.42] tracking-[-0.018em] max-sm:text-[18px]">
            {data.decision?.summary_en ?? "Decision pending."}
          </p>
          {data.decision && (
            <p className="mt-4 max-w-[64ch] text-[15px] leading-relaxed text-fm-muted">
              <span className="font-semibold text-fm-text">Next. </span>{data.decision.recommended_action}
            </p>
          )}
        </div>
        <div className="flex flex-col lg:items-end lg:text-right">
          <span className="text-[15px] font-semibold text-fm-muted">{tone.label}</span>
          <span className={cn("fm-figure fm-appear mt-2 text-[88px] leading-[0.95] max-lg:text-[72px] max-sm:text-[56px]", tone.text)} data-testid="verdict-amount">
            {formatINR(amount)}
          </span>
          {data.invoice_total_paise != null && !ok && (
            <span className="mt-3 text-[15px] text-fm-muted">of {formatINR(data.invoice_total_paise)} invoiced, incl. GST</span>
          )}
          {data.decided_at && <span className="mt-1 text-[13px] text-fm-faint">Decided {formatTs(data.decided_at)} IST</span>}
        </div>
      </div>
      <div className="mt-10 border-t border-fm-border pt-8 max-sm:mt-8 max-sm:pt-6">
        <h2 className="text-[15px] font-semibold text-fm-muted">{rules.length ? `The policy it rests on` : "Policy"}</h2>
        {rules.length ? (
          <div className={cn("mt-5 grid gap-x-12 gap-y-8", rules.length > 1 && "lg:grid-cols-2")}>
            {rules.map((r) => <ClauseQuote key={r.rule_id} rule={r} />)}
          </div>
        ) : (
          <p className="mt-3 text-[15px] text-fm-muted">All four sources agree within tolerance. No clause blocks payment.</p>
        )}
      </div>
    </section>
  );
}

/* ——— four match ——— */

function LineMatch({ line, multi }: { line: CaseLineRead; multi: boolean }) {
  const contradicted = line.evidence_source === "video" && line.observed_count !== null && line.grn_qty !== null && line.observed_count !== line.grn_qty;
  const priceOff = line.unit_price_paise !== line.po_unit_price_paise;
  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-x-3 gap-y-2">
        {multi && <span className="text-[13px] font-semibold text-fm-faint">Line {line.line_no}</span>}
        <span className="font-mono text-[14px] font-medium">{line.sku}</span>
        <span className="min-w-0 truncate text-[15px] text-fm-muted">{line.description}</span>
        {multi && line.verdict && <StatusBadge verdict={line.verdict} size="sm" className="ml-auto" />}
      </div>
      <FourMatchStrip
        size="lg"
        values={{ po: line.po_qty, grn: line.grn_qty, invoice: line.invoiced_qty, vision: line.evidence_source === "video" ? line.observed_count : null }}
        unit={line.unit}
        variancePct={line.variance_pct}
        sub={{
          po: <span className="font-mono">{formatINR(line.po_unit_price_paise)}/{line.unit}</span>,
          grn: contradicted ? <span className="font-medium text-fm-hold">contradicted · §8.4</span> : "Storekeeper signed",
          invoice: <span className={cn("font-mono", priceOff && "font-medium text-fm-hold")}>{formatINR(line.unit_price_paise)}/{line.unit}</span>,
          vision: line.evidence_source === "video" ? `${line.perception?.observed_count ?? "—"} SAM tracks` : "no dock video",
        }}
      />
      {(line.damage_count > 0 || line.evidence_quality === "insufficient") && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {line.damage_count > 0 && (
            <span className="inline-flex h-7 items-center gap-1.5 rounded-full bg-fm-hold-bg px-3 text-[13px] font-semibold text-fm-hold">
              <SignalGlyph signal="fraud" size={11} />
              {line.damage_count} damaged{line.perception?.damaged_track_ids.length ? ` · track ${line.perception.damaged_track_ids.map((t) => `#${t}`).join(", ")}` : " · per GRN"}
            </span>
          )}
          {line.evidence_quality === "insufficient" && <StatusBadge quality="insufficient" size="sm" />}
        </div>
      )}
    </div>
  );
}

/* ——— what arrived ——— */

function Arrived({ lines }: { lines: CaseLineRead[] }) {
  const video = lines.filter((l) => l.evidence_source === "video" && l.observed_count !== null);
  if (video.length === 0) return null;
  return (
    <Panel title="What arrived" subtitle="One slot per invoiced unit. Dashed slots were never seen on camera.">
      <div className="flex flex-col gap-6">
        {video.map((l) => {
          const missing = l.invoiced_qty - (l.observed_count ?? 0);
          return (
            <div key={l.po_line_id}>
              {video.length > 1 && <p className="mb-2 font-mono text-[12px] text-fm-muted">{l.sku}</p>}
              <LoadDiagram invoiced={l.invoiced_qty} observed={l.observed_count!} damaged={l.damage_count} unit={l.unit} />
              <dl className={cn("mt-4 grid gap-3 text-center", l.damage_count > 0 ? "grid-cols-4" : "grid-cols-3")}>
                {[
                  { k: "Billed", v: l.invoiced_qty, cls: "" },
                  { k: "Seen", v: l.observed_count, cls: "" },
                  { k: "Missing", v: Math.max(0, missing), cls: missing > 0 ? "text-fm-hold" : "text-fm-faint" },
                  ...(l.damage_count > 0 ? [{ k: "Damaged", v: l.damage_count, cls: "text-fm-hold" }] : []),
                ].map((x) => (
                  <div key={x.k} className="flex flex-col-reverse rounded-[12px] bg-fm-raised py-3">
                    <dt className="mt-1.5 text-[12px] font-medium text-fm-muted">{x.k}</dt>
                    <dd className={cn("fm-figure text-[28px] leading-none", x.cls)}>{x.v}</dd>
                  </div>
                ))}
              </dl>
            </div>
          );
        })}
      </div>
    </Panel>
  );
}

/* ——— page ——— */

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
      <div className="flex flex-col gap-6 pt-6" role="status" aria-label="Loading case">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-14 w-96 max-w-full" />
        <Skeleton className="h-80 w-full rounded-fm-xl" />
        <Skeleton className="h-56 w-full rounded-fm" />
      </div>
    );
  }
  if (isError || !data) {
    return (
      <div className="rounded-fm-xl bg-fm-panel">
        <ErrorState message={error instanceof Error ? error.message : "This purchase order does not exist."} action={<Button asChild size="md" variant="accent"><Link to="/cases">Back to cases</Link></Button>} />
      </div>
    );
  }

  const verdict = data.verdict;
  const totalObserved = data.lines.reduce((s, l) => s + (l.perception?.observed_count ?? 0), 0);
  const maxVisible = data.lines.reduce((m, l) => m + (l.perception?.max_visible ?? 0), 0);
  const hasPerception = data.lines.some((l) => l.perception);
  const tracks = data.lines.flatMap((l) => (l.perception?.track_ids ?? []).map((t) => ({ t, line: l, damaged: l.perception?.damaged_track_ids.includes(t) ?? false })));
  const poster = data.scenario_id ? SCENARIO_FRAMES[data.scenario_id] : undefined;
  const multi = data.lines.length > 1;

  return (
    <div className="flex flex-col gap-6">
      {/* ——— header ——— */}
      <header className="pt-4 max-sm:pt-0">
        <Link to="/cases" className="inline-flex items-center gap-1 text-[15px] text-fm-accent-text hover:underline underline-offset-4">
          <ArrowLeft size={15} aria-hidden /> Cases
        </Link>
        <div className="mt-5 flex flex-wrap items-end justify-between gap-x-8 gap-y-6">
          <div className="min-w-0">
            <p className="text-[19px] font-semibold tracking-[-0.018em] text-fm-muted">{data.vendor_name}</p>
            <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-3">
              <h1 className="text-[52px] font-bold leading-[1.02] tracking-[-0.036em] tabular-nums max-sm:text-[34px]">{data.po_number}</h1>
              <StatusBadge verdict={verdict} size="lg" />
              {data.remark?.check?.status === "not_supported" && <RemarkNotSupportedChip />}
            </div>
            <p className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-[15px] text-fm-muted">
              {data.grn_number && <span>{data.grn_number}</span>}
              {data.invoice_number && <span>Invoice {data.invoice_number}</span>}
              <span>Expected {formatDate(data.expected_date)}</span>
              {data.policy_version && <span>Policy v{data.policy_version}</span>}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button size="lg" variant="ghost" onClick={() => setAction("Override requires joint sign-off by the Purchase Manager and Finance Controller (§3.6). Request sent.")}><Undo2 size={15} /> Override</Button>
            <Button size="lg" variant="hold" onClick={() => setAction("Full hold placed. Purchase and supplier notified within 3 working days (§7.2).")}><Hand size={15} /> Hold</Button>
            {verdict === "partial_pay" && (
              <Button size="lg" variant="secondary" onClick={() => setAction(`Debit note drafted for ${formatINR(data.held_paise)}. Issue within 7 working days (§6.3).`)}><FileWarning size={15} /> Debit note</Button>
            )}
            <Button size="lg" variant="primary" onClick={() => (IS_MOCK || !data.delivery_id ? downloadPack(data) : window.open(`/api/deliveries/${data.delivery_id}/evidence-pack`))}>
              <Download size={15} /> Evidence pack
            </Button>
          </div>
        </div>
        {action && (
          <div className="fm-rise mt-5 flex items-center justify-between gap-3 rounded-full bg-fm-panel py-2 pl-5 pr-2 text-[14px]" role="status">
            <span className="flex items-center gap-2"><ShieldCheck size={16} className="shrink-0 text-fm-verified" />{action}</span>
            <button type="button" className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-fm-muted hover:bg-fm-raised" onClick={() => setAction(null)} aria-label="Dismiss"><X size={15} /></button>
          </div>
        )}
      </header>

      {verdict && <VerdictCard data={data} rules={citedRules} />}

      <Panel title="The fourth match" subtitle="PO · GRN · Invoice · Vision. The camera is the fourth source.">
        <div className="flex flex-col gap-10">
          {data.lines.map((l) => <LineMatch key={l.po_line_id} line={l} multi={multi} />)}
        </div>
      </Panel>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)]">
        <div className="flex min-w-0 flex-col gap-6">
          {data.video_url ? (
            <>
              <EvidenceVideo
                ref={player}
                src={data.video_url}
                poster={poster}
                phrase={data.lines.map((l) => l.perception?.noun_phrase).filter(Boolean).join(" + ")}
                count={hasPerception ? totalObserved : null}
                camera={data.scenario_id ? `Dock camera · ${data.scenario_id}` : "Dock camera"}
              />
              <Panel
                title="Evidence"
                subtitle={hasPerception ? `${totalObserved} unique tracks, at most ${maxVisible} visible in one frame. Tap a frame to seek.` : "Tap a frame to seek."}
              >
                <Filmstrip src={data.video_url} onSelect={(t) => player.current?.seek(t)} />
                {tracks.length > 0 && (
                  <div className="mt-6">
                    <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
                      <h3 className="text-[15px] font-semibold">SAM tracks</h3>
                      <span className="text-[12px] text-fm-faint">Score ≥ 0.80, re-entries merged in Python</span>
                    </div>
                    <ul className="flex flex-wrap gap-1.5" aria-label="SAM track IDs">
                      {tracks.map(({ t, line, damaged }) => (
                        <li
                          key={`${line.po_line_id}-${t}`}
                          title={`${line.perception?.noun_phrase} · track ${t}${damaged ? " · damaged" : ""}`}
                          className={cn("inline-flex h-8 min-w-12 items-center justify-center gap-1.5 rounded-full px-3 font-mono text-[12px]",
                            damaged ? "bg-fm-hold-bg font-medium text-fm-hold" : "bg-fm-raised text-fm-text")}
                        >
                          {damaged && <SignalGlyph signal="fraud" size={10} />}
                          {multi ? `L${line.line_no} ` : ""}#{t}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </Panel>
            </>
          ) : (
            <Panel>
              <EmptyState
                title="Documents only"
                description="No dock video exists for this delivery. The GRN count is the only receiving evidence, so the decision rests on document checks."
              />
            </Panel>
          )}

          <Panel title="Agent trace" subtitle={data.decision ? `${data.decision.model}, reasoning effort high` : undefined}>
            {data.decision ? <AgentTrace steps={data.decision.trace} /> : <p className="text-[14px] text-fm-muted">No decision recorded yet.</p>}
          </Panel>
        </div>

        <div className="flex min-w-0 flex-col gap-6">
          <Arrived lines={data.lines} />

          <Panel title="Ledger impact" subtitle="Ex-GST. Every rupee recomputed in Python after the agent records its decision.">
            <table className="w-full text-[14px]">
              <thead>
                <tr className="text-left text-[12px] font-semibold text-fm-muted">
                  <th className="pb-2 font-semibold">Line</th>
                  <th className="pb-2 text-right font-semibold">Value</th>
                  <th className="pb-2 text-right font-semibold">At risk</th>
                  <th className="pb-2 text-right font-semibold">Held</th>
                </tr>
              </thead>
              <tbody>
                {data.lines.map((l) => (
                  <tr key={l.po_line_id} className="border-t border-fm-border">
                    <td className="py-3"><span className="font-mono text-[13px]">{l.sku}</span> <Qty value={l.invoiced_qty} unit={l.unit} className="ml-1 text-[13px] text-fm-muted max-sm:hidden" /></td>
                    <td className="py-3 text-right"><Money paise={l.line_value_paise} /></td>
                    <td className="py-3 text-right"><Money paise={l.at_risk_paise} /></td>
                    <td className="py-3 text-right"><Money paise={l.held_paise} className={l.held_paise > 0 ? "font-medium text-fm-hold" : undefined} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Panel>

          {data.remark && <RemarkPanel remark={data.remark} />}

          {data.evidence_pack && <EvidenceSeal pack={data.evidence_pack} />}
        </div>
      </div>
    </div>
  );
}
