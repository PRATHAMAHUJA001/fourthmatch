import { useQuery } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, useJobEvents } from "../../lib/api";
import { cn } from "../../lib/cn";
import { formatINR } from "../../lib/format";
import type { JobEventRead, Verdict } from "../../types/api";
import { Button } from "../ui/Button";
import { FourMatchStrip } from "../ui/FourMatch";
import { StatusBadge } from "../ui/StatusBadge";
import { LiveCounter } from "../ui/LiveCounter";
import { LoadDiagram } from "../ui/LoadDiagram";
import { RouteProgress } from "../ui/RouteProgress";
import { type Stage, type StageState, stagesFor } from "../ui/Stepper";
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

/** Live pipeline view: dock video with scanline, stepper, live counter, event log, verdict. */
export function PipelineRun({ deliveryId, poId, onReset }: { deliveryId: number; poId: number; onReset?: () => void }) {
  const { events, done, error } = useJobEvents(deliveryId);
  const arrivals = useRef<number[]>([]);
  const t0 = useRef(performance.now());
  const [, force] = useState(0);
  const caseQ = useQuery({ queryKey: ["case", poId], queryFn: () => api.case(poId) });
  const logRef = useRef<HTMLOListElement>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  useEffect(() => { rootRef.current?.parentElement?.parentElement?.scrollIntoView({ behavior: "smooth", block: "start" }); }, [deliveryId]);

  useEffect(() => { t0.current = performance.now(); arrivals.current = []; }, [deliveryId]);
  if (arrivals.current.length < events.length) {
    for (let i = arrivals.current.length; i < events.length; i++) arrivals.current.push(performance.now() - t0.current);
  }
  useEffect(() => { logRef.current?.scrollTo({ top: logRef.current.scrollHeight }); }, [events.length]);
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

  const strips = c ? (
    <div className="flex flex-col gap-2.5">
      {c.lines.map((l) => (
        <FourMatchStrip
          key={l.po_line_id}
          values={{
            po: l.po_qty, grn: l.grn_qty, invoice: l.invoiced_qty,
            vision: d.states.tracking ? (reconciled ? l.observed_count : d.perLine.get(l.po_line_id) ?? 0) : null,
          }}
          unit={l.unit}
          live={tracking}
          visionPending={!d.states.tracking}
          variancePct={reconciled ? l.variance_pct : null}
          sub={{ po: l.sku, grn: "signed", invoice: "billed", vision: tracking ? "counting…" : reconciled ? "SAM tracks" : "waiting" }}
        />
      ))}
    </div>
  ) : null;

  const videoLines = (c?.lines ?? []).filter((l) => l.evidence_source === "video" && l.observed_count !== null);
  const invoicedTotal = videoLines.reduce((sum, l) => sum + l.invoiced_qty, 0);
  const units = new Set(videoLines.map((l) => l.unit));
  const unitLabel = units.size === 1 ? [...units][0] : "units";
  const decided = d.verdict !== null;
  const seenOf = (l: { po_line_id: number; observed_count: number | null }) =>
    reconciled ? l.observed_count ?? 0 : d.perLine.get(l.po_line_id) ?? 0;
  const seenTotal = videoLines.reduce((sum, l) => sum + seenOf(l), 0);
  const activeStage = d.stages.find((s) => d.states[s.key] === "active");

  const hero = (
    <section className="fm-amber-block flex min-w-0 flex-col rounded-fm" aria-label="Active delivery">
      <div className="flex items-start justify-between gap-3 px-5 pt-4">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5 font-cond text-[11px] font-semibold uppercase tracking-[0.1em] opacity-75">
            {!done && <span className="fm-live-dot h-1.5 w-1.5 rounded-full bg-current" aria-hidden />}
            {done ? "Delivery checked" : "Active delivery"} · Bay 01
          </div>
          <h2 className="mt-1.5 truncate font-mono text-[30px] max-sm:text-[22px] font-medium leading-none tracking-[-0.04em]">{c?.po_number ?? "···"}</h2>
          <p className="mt-1.5 truncate text-[15px] font-semibold tracking-[-0.01em]">{c?.vendor_name ?? "Loading delivery…"}</p>
        </div>
        <span className="shrink-0 rounded-fm-sm border border-black/25 px-1.5 py-1 font-mono text-[10.5px] font-medium uppercase leading-none tracking-[0.04em]">
          {decided ? "Decided" : activeStage?.short ?? "Queued"}
        </span>
      </div>
      <div className="flex flex-1 flex-col justify-center px-5 pb-2 pt-3">
        {videoLines.length > 0 ? (
          <div className={cn("grid gap-x-4 gap-y-1", videoLines.length > 1 && "sm:grid-cols-2")}>
            {videoLines.map((l) => (
              <div key={l.po_line_id} className="min-w-0">
                {videoLines.length > 1 && <div className="mb-0.5 truncate font-mono text-[10.5px] opacity-70">{l.sku}</div>}
                <LoadDiagram
                  tone="ink" solid pending={!decided}
                  invoiced={l.invoiced_qty} observed={seenOf(l)} damaged={reconciled ? l.damage_count : 0} unit={l.unit}
                  className={videoLines.length > 1 ? "max-h-[96px]" : undefined}
                />
              </div>
            ))}
          </div>
        ) : (
          <div className="flex h-[120px] items-center text-[12.5px] opacity-70">{c ? "No dock video for this delivery." : "Loading delivery…"}</div>
        )}
      </div>
      <dl className="mt-auto grid grid-cols-3 border-t border-black/15">
        {[
          { k: "Invoiced", v: <span>{invoicedTotal}<span className="ml-1 font-sans text-[12px] font-normal opacity-65">{unitLabel}</span></span> },
          { k: "Seen on video", v: <span className="inline-flex items-baseline"><LiveCounter value={seenTotal} digits={Math.max(2, String(invoicedTotal).length)} label="Seen on video" className="text-[28px]" /><span className="ml-1 font-sans text-[12px] opacity-65">{!decided && tracking ? "live" : unitLabel}</span></span> },
          { k: "Held", v: decided ? formatINR(d.verdict!.held_paise) : <span className="opacity-40">—</span> },
        ].map((x, i) => (
          <div key={x.k} className={cn("min-w-0 px-5 py-3", i > 0 && "border-l border-black/15")}>
            <dt className="font-cond text-[11px] font-semibold uppercase tracking-[0.1em] opacity-70">{x.k}</dt>
            <dd className="mt-1 truncate font-mono text-[28px] font-medium leading-none tracking-[-0.04em] tabular-nums">{x.v}</dd>
          </div>
        ))}
      </dl>
    </section>
  );

  const video = c?.video_url ? (
    <EvidenceVideo
      src={c.video_url}
      phrase={phrase ?? null}
      count={d.states.tracking ? d.tracks : null}
      countLabel={tracking ? "Tracking" : "Unique tracks"}
      scanning={tracking || d.states.understanding === "active" || d.states.damage_check === "active"}
      camera={`DOCK-01 · ${c.po_number}`}
    />
  ) : (
    <div className="fm-dotgrid flex aspect-video items-center justify-center rounded-fm border border-fm-border bg-fm-sunken text-[12px] text-fm-muted">Loading footage…</div>
  );

  return (
    <div ref={rootRef} className="flex scroll-mt-4 flex-col gap-3">
      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        {hero}
        <div className="min-w-0">{video}</div>
      </div>

      <div className="rounded-fm border border-fm-border bg-fm-panel px-3 pb-2 pt-2.5">
        <div className="mb-1 flex items-center justify-between">
          <span className="fm-label">Pipeline</span>
          <span className="font-mono text-[11px] tabular-nums text-fm-muted">T+{elapsed.toFixed(1)}s</span>
        </div>
        <RouteProgress stages={d.stages} states={d.states} timing={d.timing} />
      </div>

      <div className="grid gap-3 lg:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
        <div className="flex min-w-0 flex-col gap-3">{strips}</div>
        <div className="flex min-w-0 flex-col gap-3">
          {d.verdict && c && (
            <div className={cn("fm-rise rounded-fm border p-3.5", d.verdict.verdict === "approve" ? "border-fm-verified-line bg-fm-verified-bg" : "border-fm-hold bg-fm-hold-bg")}>
              <div className="flex items-center justify-between gap-2">
                <StatusBadge verdict={d.verdict.verdict} size="lg" />
                <span className="font-mono text-[11px] text-fm-muted">{(c.clauses ?? []).map((x) => `§${x}`).join(" · ")}</span>
              </div>
              <div className="mt-3 flex items-end justify-between gap-3">
                <div>
                  <div className="fm-label">{d.verdict.verdict === "approve" ? "Released" : "Held"}</div>
                  <div className={cn("font-mono text-[30px] font-medium leading-none tracking-[-0.04em]", d.verdict.verdict === "approve" ? "text-fm-verified" : "text-fm-hold")}>
                    {formatINR(d.verdict.verdict === "approve" ? c.invoice_total_paise ?? c.total_paise : d.verdict.held_paise)}
                  </div>
                </div>
                <Button asChild variant="primary" size="sm"><Link to={`/cases/${poId}`}>Open case <ArrowRight size={13} /></Link></Button>
              </div>
            </div>
          )}
          <div className="rounded-fm border border-fm-border bg-fm-sunken">
            <div className="flex items-center justify-between border-b border-fm-border px-3 py-1.5">
              <span className="fm-label">job_events</span>
              <span className="font-mono text-[10.5px] text-fm-faint">SSE · {events.length} stored · T+{elapsed.toFixed(1)}s</span>
            </div>
            <ol ref={logRef} className="fm-scroll h-[132px] overflow-auto px-3 py-2 font-mono text-[11px] leading-[1.7]" aria-live="polite">
              {events.map((e, i) => (
                <li key={e.seq} className={cn("flex gap-2", e.event_type.endsWith("_progress") ? "text-fm-faint" : "text-fm-muted", e.event_type === "verdict" && "text-fm-hold")}>
                  <span className="w-12 shrink-0 tabular-nums text-fm-faint">{((arrivals.current[i] ?? 0) / 1000).toFixed(2)}</span>
                  <span className="w-[150px] shrink-0 truncate text-fm-text">{e.event_type}</span>
                  <span className="truncate">{e.message}</span>
                </li>
              ))}
              {!done && <li className="fm-live-dot text-fm-faint">▍</li>}
            </ol>
          </div>
          {error && <p className="text-[12px] text-fm-fraud" role="alert">{error}</p>}
          {done && onReset && <Button variant="ghost" size="sm" onClick={onReset} className="self-start">Run another delivery</Button>}
        </div>
      </div>
    </div>
  );
}
