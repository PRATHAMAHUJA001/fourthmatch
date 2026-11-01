import { useQuery } from "@tanstack/react-query";
import { ArrowRight, RotateCcw } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, useJobEvents } from "../../lib/api";
import { cn } from "../../lib/cn";
import { formatINR, plural } from "../../lib/format";
import { SCENARIO_FRAMES } from "../../lib/media";
import type { JobEventRead, Verdict } from "../../types/api";
import { Button } from "../ui/Button";
import { FourMatchStrip } from "../ui/FourMatch";
import { StatusBadge } from "../ui/StatusBadge";
import { LiveCounter } from "../ui/LiveCounter";
import { LoadDiagram } from "../ui/LoadDiagram";
import { type Stage, type StageState, Stepper, stagesFor } from "../ui/Stepper";
import { EvidenceVideo } from "./EvidenceVideo";

function baseOf(t: string) {
  return t.replace(/_(finished|progress)$/, "");
}

/** Derives stepper state, timings and the live counter from stored job events. */
export function derive(events: JobEventRead[], arrivals: number[]) {
  // The remark stage exists only when the upload carried one (queued payload) or its events appear.
  const hasRemark = events.some(
    (e) => e.event_type.startsWith("transcribing_remark") || (e.payload as { has_remark?: boolean }).has_remark === true,
  );
  const stages: Stage[] = stagesFor(hasRemark);
  const STAGE_KEYS = stages.map((s) => s.key);
  const states: Record<string, StageState> = {};
  const started: Record<string, number> = {};
  const timing: Record<string, number> = {};
  let tracks = 0;
  const perLine = new Map<number, number>();
  let verdict: { verdict: Verdict; held_paise: number } | null = null;
  let failed = false;
  events.forEach((e, i) => {
    const at = arrivals[i] ?? 0;
    const b = baseOf(e.event_type);
    if (e.event_type === "failed") { failed = true; return; }
    // Optional stage failing is non-fatal: the pipeline carries on without the remark.
    if (e.event_type === "transcribing_remark_failed") { states.transcribing_remark = "failed"; return; }
    if (e.event_type === "done") {
      for (const k of STAGE_KEYS) { if (states[k] !== "done" && states[k] !== "failed") { states[k] = "done"; if (started[k] != null) timing[k] = at - started[k]; } }
      return;
    }
    if (!STAGE_KEYS.includes(b)) return;
    if (e.event_type.endsWith("_progress")) {
      const p = e.payload as { tracks?: number; po_line_id?: number };
      if (p.po_line_id != null && p.tracks != null) perLine.set(p.po_line_id, p.tracks);
      tracks = [...perLine.values()].reduce((s, x) => s + x, 0);
      return;
    }
    if (e.event_type.endsWith("_finished")) {
      states[b] = "done";
      timing[b] = at - (started[b] ?? at);
      return;
    }
    // a new stage starting closes any open earlier stage
    const idx = STAGE_KEYS.indexOf(b);
    STAGE_KEYS.slice(0, idx).forEach((k) => {
      if (states[k] === "active") { states[k] = "done"; timing[k] = at - (started[k] ?? at); }
    });
    states[b] = "active";
    started[b] = at;
    if (b === "verdict") verdict = e.payload as { verdict: Verdict; held_paise: number };
  });
  if (failed) for (const k of STAGE_KEYS) if (states[k] === "active") states[k] = "failed";
  return { stages, states, timing, tracks, perLine, verdict: verdict as { verdict: Verdict; held_paise: number } | null, failed };
}

/** Live pipeline view: the dock video, the count ticking from stored tracking_progress events,
 *  an elegant stepper, the four sources resolving and the verdict arriving. Everything shown is
 *  read from job_events (SSE streams only what is stored) or the case API. */
export function PipelineRun({ deliveryId, poId, onReset }: { deliveryId: number; poId: number; onReset?: () => void }) {
  const { events, done, error } = useJobEvents(deliveryId);
  const arrivals = useRef<number[]>([]);
  const t0 = useRef(performance.now());
  const [, force] = useState(0);
  const caseQ = useQuery({ queryKey: ["case", poId], queryFn: () => api.case(poId) });
  const logRef = useRef<HTMLOListElement>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  useEffect(() => { rootRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }); }, [deliveryId]);

  useEffect(() => { t0.current = performance.now(); arrivals.current = []; }, [deliveryId]);
  if (arrivals.current.length < events.length) {
    for (let i = arrivals.current.length; i < events.length; i++) arrivals.current.push(performance.now() - t0.current);
  }
  useEffect(() => { logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" }); }, [events.length]);
  useEffect(() => {
    if (done) return;
    const t = setInterval(() => force((x) => x + 1), 100);
    return () => clearInterval(t);
  }, [done]);

  const d = useMemo(() => derive(events, arrivals.current), [events]);
  const c = caseQ.data;
  const tracking = d.states.tracking === "active";
  const elapsed = (done && arrivals.current.length ? arrivals.current[arrivals.current.length - 1] : performance.now() - t0.current) / 1000;
  const reconciled = d.states.reconciling === "done" || d.states.reconciling === "active" || done;
  const phrase = (events.find((e) => e.event_type === "understanding_finished")?.payload as { phrases?: string[] } | undefined)?.phrases?.join(" + ");

  const videoLines = (c?.lines ?? []).filter((l) => l.evidence_source === "video" && l.observed_count !== null);
  const invoicedTotal = videoLines.reduce((sum, l) => sum + l.invoiced_qty, 0);
  const units = new Set(videoLines.map((l) => l.unit));
  const unitLabel = units.size === 1 ? [...units][0] : "units";
  const decided = d.verdict !== null;
  const seenOf = (l: { po_line_id: number; observed_count: number | null }) =>
    reconciled ? l.observed_count ?? 0 : d.perLine.get(l.po_line_id) ?? 0;
  const seenTotal = videoLines.reduce((sum, l) => sum + seenOf(l), 0);
  const activeStage = d.stages.find((s) => d.states[s.key] === "active");
  const status = d.failed ? "Failed" : decided && done ? "Decided" : activeStage?.label ?? (events.length ? "Starting" : "Queued");
  const poster = c?.scenario_id ? SCENARIO_FRAMES[c.scenario_id] : undefined;

  const verdict = d.verdict && c ? (
    <div className="fm-appear flex flex-col" aria-live="polite">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <StatusBadge verdict={d.verdict.verdict} size="lg" />
        {(c.clauses ?? []).length > 0 && <span className="text-[13px] text-fm-muted">Clause {(c.clauses ?? []).join(", ")}</span>}
      </div>
      <div className="mt-4 flex items-baseline gap-3">
        <span className={cn("fm-figure text-[56px] leading-none max-sm:text-[44px]", d.verdict.verdict === "approve" ? "text-fm-verified" : "text-fm-hold")}>
          {formatINR(d.verdict.verdict === "approve" ? c.invoice_total_paise ?? c.total_paise : d.verdict.held_paise)}
        </span>
        <span className="text-[17px] font-semibold text-fm-muted">{d.verdict.verdict === "approve" ? "released" : "held"}</span>
      </div>
      <div className="mt-5 flex flex-wrap gap-2">
        <Button asChild variant="accent" size="lg"><Link to={`/cases/${poId}`}>Open case <ArrowRight size={15} /></Link></Button>
        {done && onReset && <Button variant="ghost" size="lg" onClick={onReset}><RotateCcw size={14} /> Run another</Button>}
      </div>
    </div>
  ) : null;

  return (
    <div ref={rootRef} className="flex scroll-mt-[calc(var(--fm-nav-h)+24px)] flex-col gap-6" data-testid="pipeline-run">
      {/* ——— run header ——— */}
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
        <div className="min-w-0">
          <p className="text-[17px] font-semibold tracking-[-0.014em] text-fm-muted">{c?.vendor_name ?? "Loading delivery…"}</p>
          <h2 className="mt-1 truncate text-[40px] font-bold leading-none tracking-[-0.034em] tabular-nums max-sm:text-[28px]">{c?.po_number ?? "\u00a0"}</h2>
        </div>
        <div className="flex items-center gap-4">
          <span className={cn("inline-flex h-9 items-center gap-2 rounded-full px-4 text-[14px] font-semibold",
            d.failed ? "bg-fm-fraud-bg text-fm-fraud" : decided && done ? "bg-fm-raised text-fm-text" : "bg-fm-info-bg text-fm-accent-text")}>
            {!done && !d.failed && <span className="fm-live-dot h-2 w-2 rounded-full bg-current" aria-hidden />}
            {status}
          </span>
          <span className="font-mono text-[14px] tabular-nums text-fm-muted" aria-label="Elapsed">{elapsed.toFixed(1)}s</span>
        </div>
      </div>

      {/* ——— footage + live count ——— */}
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        {c?.video_url ? (
          <EvidenceVideo
            src={c.video_url}
            poster={poster}
            phrase={phrase ?? null}
            count={d.states.tracking ? d.tracks : null}
            countLabel={tracking ? "Tracking" : "Unique tracks"}
            scanning={tracking || d.states.understanding === "active" || d.states.damage_check === "active"}
            camera={`Bay 01 · ${c.po_number}`}
          />
        ) : (
          <div className="flex aspect-video items-center justify-center rounded-fm-xl bg-fm-panel text-[15px] text-fm-muted">{c ? "No dock video for this delivery." : "Loading footage…"}</div>
        )}
        <section className="flex min-w-0 flex-col rounded-fm-xl bg-fm-panel p-8 max-sm:p-6" aria-label="Seen on video">
          {videoLines.length > 0 ? (
            <>
              <p className="text-[15px] font-semibold text-fm-muted">Seen on video</p>
              <div className="mt-3 flex items-baseline gap-3">
                <LiveCounter value={seenTotal} label="Seen on video" className={cn("text-[96px] leading-[0.9] max-sm:text-[72px]", reconciled && seenTotal < invoicedTotal && "text-fm-hold")} />
                <span className="text-[19px] font-medium text-fm-muted">of {invoicedTotal} {plural(unitLabel, invoicedTotal)} invoiced</span>
              </div>
              <p className="mt-2 text-[13px] text-fm-faint">{tracking ? "One step per track SAM confirms." : reconciled ? "Unique tracks, merged and counted in Python." : d.states.tracking ? "" : "Waiting for sam-3.1."}</p>
              <div className={cn("mt-5 grid gap-4", videoLines.length > 1 && "grid-cols-2", verdict && "max-w-[78%] max-lg:max-w-none")}>
                {videoLines.map((l) => (
                  <div key={l.po_line_id} className="min-w-0">
                    {videoLines.length > 1 && <div className="mb-1 truncate font-mono text-[12px] text-fm-muted">{l.sku}</div>}
                    <LoadDiagram solid pending={!decided} invoiced={l.invoiced_qty} observed={seenOf(l)} damaged={reconciled ? l.damage_count : 0} unit={l.unit} />
                  </div>
                ))}
              </div>
            </>
          ) : (
            <p className="text-[15px] text-fm-muted">{c ? "Documents only. The GRN is the receiving evidence." : "Loading delivery…"}</p>
          )}
          <div className="mt-auto pt-6">
            {verdict ? <div className="border-t border-fm-border pt-6">{verdict}</div> : (
              <p className="border-t border-fm-border pt-5 text-[14px] text-fm-faint">{d.failed ? "The run stopped before a decision." : "The decision agent rules once all four sources are in."}</p>
            )}
          </div>
        </section>
      </div>

      {/* ——— stepper ——— */}
      <section className="rounded-fm-xl bg-fm-panel px-8 pb-6 pt-8 max-sm:px-5 max-sm:pt-6" aria-label="Pipeline">
        <Stepper stages={d.stages} states={d.states} timing={d.timing} />
      </section>

      {/* ——— four sources + verdict / log ——— */}
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <section className="flex min-w-0 flex-col gap-6 rounded-fm-xl bg-fm-panel p-8 max-sm:p-5" aria-label="Four-way match">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h3 className="text-[19px] font-semibold tracking-[-0.022em]">The fourth match</h3>
            <span className="text-[13px] text-fm-muted">{reconciled ? "Reconciled in Python" : tracking ? "Vision is counting" : "Vision pending"}</span>
          </div>
          {c?.lines.map((l) => (
            <div key={l.po_line_id}>
              {c.lines.length > 1 && <p className="mb-2 font-mono text-[12px] text-fm-muted">{l.sku}</p>}
              <FourMatchStrip
                values={{
                  po: l.po_qty, grn: l.grn_qty, invoice: l.invoiced_qty,
                  vision: d.states.tracking ? (reconciled ? l.observed_count : d.perLine.get(l.po_line_id) ?? 0) : null,
                }}
                unit={l.unit}
                live={tracking}
                visionPending={!d.states.tracking}
                variancePct={reconciled ? l.variance_pct : null}
                sub={{ po: <span className="font-mono">{l.sku}</span>, grn: "Signed", invoice: "Billed", vision: tracking ? "Counting…" : reconciled ? "SAM tracks" : "Waiting" }}
              />
            </div>
          ))}
        </section>
        <div className="flex min-w-0 flex-col gap-6">
          <section className="flex min-h-0 flex-1 flex-col rounded-fm-xl bg-fm-panel p-8 max-sm:p-5" aria-label="Event log">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h3 className="text-[19px] font-semibold tracking-[-0.022em]">Event log</h3>
              <span className="text-[13px] text-fm-muted">{events.length} stored · streamed over SSE</span>
            </div>
            <ol ref={logRef} className={"fm-scroll mt-4 max-h-[260px] overflow-auto text-[13px] leading-[1.5]"} aria-live="off">
              {events.map((e, i) => {
                const progress = e.event_type.endsWith("_progress");
                return (
                  <li key={e.seq} className={cn("fm-rise flex gap-3 py-1", progress ? "text-fm-faint" : "text-fm-text", e.event_type === "verdict" && "font-semibold")}>
                    <span className="w-11 shrink-0 text-right font-mono text-[12px] tabular-nums text-fm-faint">{((arrivals.current[i] ?? 0) / 1000).toFixed(1)}s</span>
                    <span className="min-w-0">{e.message}</span>
                  </li>
                );
              })}
            </ol>
            {error && <p className="mt-3 text-[13px] text-fm-fraud" role="alert">{error}</p>}
          </section>
        </div>
      </div>
    </div>
  );
}
