/** The signature scroll story. One sticky stage, four chapters, driven by scroll progress:
 *  paper says N → the camera saw M (count ticks from SAM data) → four sources, one disagrees
 *  (vision turns amber) → payment held, clause cited. Every figure comes from the case API.
 *  Under prefers-reduced-motion the chapters render as plain stacked sections in their final state. */
import { Lock } from "lucide-react";
import { useRef, type CSSProperties, type ReactNode } from "react";
import { DemoSealNote } from "../../components/evidence/EvidenceSeal";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { IS_MOCK } from "../../lib/demo";
import { SignalGlyph } from "../../components/ui/Glyph";
import { cn } from "../../lib/cn";
import { formatINR, formatPct, shortHash } from "../../lib/format";
import { easeOut, range, useReducedMotion, useReveal, useScrollProgress } from "../../lib/motion";
import type { CaseDetail, CaseLineRead } from "../../types/api";
import { excerpt, videoClause } from "./content";

export interface StoryProps {
  detail: CaseDetail;
  line: CaseLineRead;
  /** Real dock frame from this case's video (public/media). */
  frame: string;
}

const N = 4;
const FADE = 0.04;

/** Opacity of chapter i at overall progress p: sequential fade out / fade in at each boundary. */
function chapterOpacity(p: number, i: number) {
  const a = i / N, b = (i + 1) / N;
  const fin = i === 0 ? 1 : range(p, a, a + FADE * 1.6);
  const fout = i === N - 1 ? 1 : 1 - range(p, b - FADE, b);
  return Math.min(fin, fout);
}

const plural = (unit: string, n: number) => (n === 1 ? unit : unit.endsWith("x") ? `${unit}es` : `${unit}s`);

/* ——— chapters ——— */

function PaperChapter({ detail, line }: StoryProps) {
  const ref = useReveal<HTMLDivElement>(0.2);
  const agree = line.po_qty === line.grn_qty && line.grn_qty === line.invoiced_qty;
  const docs = [
    { k: "Purchase order", v: line.po_qty, id: detail.po_number },
    { k: "Goods receipt", v: line.grn_qty, id: detail.grn_number },
    { k: "Invoice", v: line.invoiced_qty, id: detail.invoice_number },
  ];
  return (
    <div ref={ref} className="mx-auto w-full max-w-[1200px] px-6 text-center">
      <p className="fm-eyebrow fm-reveal text-fm-muted">{detail.vendor_name}</p>
      <h2 className="fm-display fm-reveal mt-3" style={{ "--fm-delay": "80ms" } as CSSProperties}>
        {agree ? <>Paper says <span className="fm-figure">{line.po_qty}</span>.</> : <>The paperwork disagrees.</>}
      </h2>
      <p className="fm-lede fm-reveal mx-auto mt-5 max-w-[38ch] text-fm-muted" style={{ "--fm-delay": "160ms" } as CSSProperties}>
        Three documents. Three signatures. One {line.unit === "box" ? "carton" : line.unit} count.
      </p>
      <div className="mx-auto mt-14 grid max-w-[960px] grid-cols-3 max-sm:mt-10">
        {docs.map((d, i) => (
          <div key={d.k} className={cn("fm-reveal px-2", i > 0 && "border-l border-fm-border")} style={{ "--fm-delay": `${260 + i * 110}ms` } as CSSProperties}>
            <div className="fm-figure text-[clamp(72px,12vw,168px)] leading-none">{d.v ?? "—"}</div>
            <div className="mt-4 text-[15px] font-semibold tracking-[-0.012em] max-sm:text-[13px]">{d.k}</div>
            <div className="mt-1 truncate font-mono text-[12px] text-fm-faint max-sm:text-[10.5px]">{d.id}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function CameraChapter({ line, t, frame, detail }: StoryProps & { t: number }) {
  const observed = line.observed_count ?? 0;
  const tracks = line.perception?.track_ids ?? [];
  // The figure only steps through real integers: one per SAM track ID lighting up. With no
  // track list to reveal, it shows the measured count directly.
  const lit = Math.round(tracks.length * easeOut(range(t, 0.08, 0.62)));
  const count = tracks.length ? lit : observed;
  return (
    <div className="relative h-full w-full overflow-hidden bg-black text-white">
      <img
        src={frame}
        alt="Receiving dock camera frame: cartons on the floor"
        width={1280}
        height={720}
        className="absolute inset-0 h-full w-full object-cover will-change-transform"
        style={{ transform: `scale(${1.08 - 0.08 * easeOut(t)})` }}
      />
      <div className="absolute inset-0 bg-[linear-gradient(90deg,rgba(0,0,0,0.82)_0%,rgba(0,0,0,0.6)_38%,rgba(0,0,0,0.1)_75%,rgba(0,0,0,0)_100%)] max-md:bg-[linear-gradient(0deg,rgba(0,0,0,0.82)_0%,rgba(0,0,0,0.5)_55%,rgba(0,0,0,0.15)_100%)]" />
      <div className="relative mx-auto grid h-full max-w-[1200px] grid-cols-12 items-center px-6 max-md:items-end max-md:pb-16">
        <div className="col-span-12 md:col-span-7">
          <p className="fm-eyebrow text-white/70">sam-3.1 tracks every carton</p>
          <h2 className="fm-display mt-3">
            The camera saw{" "}
            <span className="fm-figure text-[var(--fm-amber-fixed)]" aria-hidden>
              {count}
            </span>
            <span className="sr-only">{observed}</span>.
          </h2>
          <p className="fm-lede mt-5 max-w-[32ch] text-white/80">
            Every “{line.perception?.noun_phrase ?? line.unit}” followed across the footage. {observed} unique tracks, counted in Python.
          </p>
          {tracks.length > 0 && (
            <ul className="mt-8 grid w-max grid-cols-6 gap-2" aria-label="SAM track IDs">
              {tracks.map((id, i) => (
                <li
                  key={id}
                  className={cn(
                    "flex h-7 min-w-11 items-center justify-center rounded-full px-2.5 font-mono text-[12px] transition-colors duration-300",
                    i < count ? "bg-white text-black" : "bg-white/12 text-white/50",
                  )}
                >
                  #{id}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
      <p className="absolute bottom-5 right-6 text-[12px] text-white/55 max-md:hidden">Dock camera{detail.scenario_id ? ` · ${detail.scenario_id}` : ""} · synthetic footage</p>
    </div>
  );
}

function MatchChapter({ line, t, detail }: StoryProps & { t: number }) {
  const flagged = t > 0.32;
  const rule = videoClause(line.cited_rules);
  const tiles = [
    { k: "PO", sub: "Purchase order", v: line.po_qty },
    { k: "GRN", sub: "Signed at the dock", v: line.grn_qty },
    { k: "Invoice", sub: "Vendor invoice", v: line.invoiced_qty },
    { k: "Vision", sub: "Dock video", v: line.observed_count, vision: true },
  ];
  const differs = line.observed_count !== null && line.observed_count !== line.po_qty;
  return (
    <div className="mx-auto w-full max-w-[1200px] px-6">
      <div className="grid grid-cols-12 items-end gap-y-4">
        <h2 className="fm-display col-span-12 lg:col-span-8">Four sources. {differs ? "One disagrees." : "All agree."}</h2>
        <p className="fm-lede col-span-12 text-fm-muted lg:col-span-4 lg:pb-2">
          The storekeeper signed for {line.grn_qty}.{rule && differs ? ` Under clause ${rule.source_clause}, the video prevails.` : ""}
        </p>
      </div>
      <div className="mt-12 grid grid-cols-4 gap-4 max-md:mt-8 max-md:grid-cols-2 max-md:gap-3">
        {tiles.map((x, i) => {
          const amber = x.vision && differs && flagged;
          return (
            <div
              key={x.k}
              className={cn(
                "flex h-[clamp(200px,38svh,340px)] flex-col justify-between rounded-fm-xl p-6 transition-[background-color,box-shadow,transform] duration-500 ease-[var(--fm-ease)] max-md:h-[clamp(150px,22svh,200px)] max-md:p-5",
                amber ? "bg-fm-hold-bg shadow-[inset_0_0_0_2px_var(--fm-hold-fill)]" : "bg-fm-tile",
              )}
              style={{ opacity: range(t, 0.02 + i * 0.05, 0.14 + i * 0.05), transform: `translateY(${(1 - range(t, 0.02 + i * 0.05, 0.16 + i * 0.05)) * 24}px)` }}
            >
              <div className="flex items-center justify-between">
                <span className={cn("text-[17px] font-semibold tracking-[-0.016em]", amber && "text-fm-hold")}>{x.k}</span>
                {amber && <span className="flex items-center gap-1.5 text-[13px] font-semibold text-fm-hold"><SignalGlyph signal="hold" size={13} />≠ PO</span>}
              </div>
              <div>
                <div className={cn("fm-figure text-[clamp(64px,8vw,120px)] leading-none transition-colors duration-500", amber && "text-fm-hold")}>{x.v ?? "—"}</div>
                <div className="mt-3 text-[14px] text-fm-muted">
                  {amber && line.variance_pct != null ? <span className="font-mono font-medium text-fm-hold">{formatPct(line.variance_pct)} vs PO</span> : x.sub}
                </div>
              </div>
            </div>
          );
        })}
      </div>
      <p className="sr-only">{detail.po_number}</p>
    </div>
  );
}

function VerdictChapter({ detail, line, t }: StoryProps & { t: number }) {
  // Money is never tweened: the computed figure fades and settles in, nothing in between.
  const appear = easeOut(range(t, 0.04, 0.32));
  const rules = line.cited_rules;
  const short = line.observed_count !== null ? line.invoiced_qty - line.observed_count : null;
  return (
    <div className="mx-auto grid w-full max-w-[1200px] grid-cols-12 items-center gap-x-6 gap-y-8 px-6">
      <div className="col-span-12 lg:col-span-5">
        <h2 className="fm-title">Payment held.<br />Clause cited.</h2>
        <p className="fm-lede mt-5 max-w-[30ch] text-fm-muted">
          {short && short > 0 ? `${short} ${plural(line.unit, short)} never arrived, so they are not paid for. ` : ""}
          {detail.decision?.recommended_action}
        </p>
      </div>
      <div className="col-span-12 rounded-fm-xl bg-fm-tile p-8 max-sm:p-6 lg:col-span-7">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <StatusBadge verdict={detail.verdict} size="lg" />
          <span className="font-mono text-[12px] text-fm-faint">{detail.po_number}</span>
        </div>
        <div className="mt-8 flex items-baseline gap-3">
          <span
            className="fm-figure origin-left text-[clamp(56px,6.4vw,96px)] leading-none text-fm-hold will-change-transform"
            style={{ opacity: appear, transform: `scale(${0.94 + 0.06 * appear})` }}
            data-testid="story-held"
          >
            {formatINR(detail.held_paise)}
          </span>
          <span className="text-[17px] font-semibold text-fm-muted">held</span>
        </div>
        <ul className="mt-8 flex flex-col gap-5 border-t border-fm-border pt-6">
          {rules.map((r) => (
            <li key={r.rule_id} className="grid grid-cols-[64px_1fr] gap-4 max-sm:grid-cols-[52px_1fr]">
              <span className="font-mono text-[17px] font-medium">§{r.source_clause}</span>
              <blockquote className="line-clamp-3 text-[15px] leading-[1.5] text-fm-muted max-sm:text-[14px]">“{excerpt(r.source_text)}”</blockquote>
            </li>
          ))}
        </ul>
        {detail.evidence_pack && (IS_MOCK ? (
          <DemoSealNote className="mt-6 border-t border-fm-border pt-5" />
        ) : (
          <p className="mt-6 flex flex-wrap items-center gap-x-2 gap-y-1 border-t border-fm-border pt-5 text-[13px] text-fm-muted">
            <Lock size={14} strokeWidth={2} aria-hidden />
            Evidence pack sealed
            <span className="whitespace-nowrap font-mono text-fm-text">sha256 {shortHash(detail.evidence_pack.sha256, 10)}</span>
          </p>
        ))}
      </div>
    </div>
  );
}

/* ——— stage ——— */

function Layer({ opacity, children, className, dark }: { opacity: number; children: ReactNode; className?: string; dark?: boolean }) {
  return (
    <div
      data-nav-dark={dark && opacity > 0.5 ? "" : undefined}
      className={cn("absolute inset-0 flex items-center", className)}
      style={{ opacity, visibility: opacity < 0.01 ? "hidden" : "visible", pointerEvents: opacity > 0.5 ? "auto" : "none" }}
      aria-hidden={opacity < 0.5}
    >
      {children}
    </div>
  );
}

export function Story(props: StoryProps) {
  const reduce = useReducedMotion();
  const ref = useRef<HTMLElement>(null);
  const p = useScrollProgress(ref, !reduce);

  if (reduce) {
    return (
      <section aria-label="What happened on PO delivery" className="bg-fm-canvas">
        <div className="py-32"><PaperChapter {...props} /></div>
        <div className="h-[80svh] min-h-[560px]" data-nav-dark><CameraChapter {...props} t={1} /></div>
        <div className="py-32"><MatchChapter {...props} t={1} /></div>
        <div className="py-32"><VerdictChapter {...props} t={1} /></div>
      </section>
    );
  }

  const t = (i: number) => range(p, i / N, (i + 1) / N);
  const o = [0, 1, 2, 3].map((i) => chapterOpacity(p, i));
  return (
    <section ref={ref} aria-label="What happened on this delivery" className="relative h-[480svh] bg-fm-canvas" data-testid="story">
      <div className="sticky top-0 h-[100svh] overflow-hidden">
        <Layer opacity={o[0]} className="pt-[var(--fm-nav-h)]"><PaperChapter {...props} /></Layer>
        <Layer opacity={o[1]} dark><CameraChapter {...props} t={t(1)} /></Layer>
        <Layer opacity={o[2]} className="pt-[var(--fm-nav-h)]"><MatchChapter {...props} t={t(2)} /></Layer>
        <Layer opacity={o[3]} className="pt-[var(--fm-nav-h)]"><VerdictChapter {...props} t={t(3)} /></Layer>
        <ol className="absolute bottom-6 left-1/2 flex -translate-x-1/2 gap-1.5" aria-hidden>
          {o.map((_, i) => (
            <li key={i} className={cn("h-1 w-8 overflow-hidden rounded-full", i === 1 && o[1] > 0.5 ? "bg-white/25" : "bg-fm-hover")}>
              <span className={cn("block h-full origin-left rounded-full", i === 1 && o[1] > 0.5 ? "bg-white" : "bg-fm-text")} style={{ transform: `scaleX(${t(i)})` }} />
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
