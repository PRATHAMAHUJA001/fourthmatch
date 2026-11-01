/** Landing sections below the story. Real media only (public/media, extracted from the
 *  project's own videos and outputs); every number comes from the API / mock dataset. */
import { ArrowUpRight } from "lucide-react";
import { useRef, type CSSProperties, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { typeLabel } from "../analytics/labels";
import { cn } from "../../lib/cn";
import { formatINR } from "../../lib/format";
import { easeOut, range, useReducedMotion, useReveal, useScrollProgress } from "../../lib/motion";
import type { CaseLineRead, CaseSummary, EvalResults } from "../../types/api";
import { excerpt, SCENARIO_FRAMES, videoClause } from "./content";

function Reveal({ children, delay = 0, className, as: As = "div" }: { children: ReactNode; delay?: number; className?: string; as?: "div" | "li" | "p" | "h2" }) {
  const ref = useReveal<HTMLDivElement>();
  return (
    <As ref={ref as never} className={cn("fm-reveal", className)} style={{ "--fm-delay": `${delay}ms` } as CSSProperties}>
      {children}
    </As>
  );
}

const Container = ({ children, className }: { children: ReactNode; className?: string }) => (
  <div className={cn("mx-auto w-full max-w-[1200px] px-6", className)}>{children}</div>
);

/* ——— SAM reveal: raw photo wipes to masks + track IDs as you scroll ——— */
export function SamReveal() {
  const reduce = useReducedMotion();
  const ref = useRef<HTMLElement>(null);
  const p = useScrollProgress(ref, !reduce);
  const w = reduce ? 1 : easeOut(range(p, 0.18, 0.78));
  return (
    <section ref={ref} data-nav-dark className={cn("relative bg-black text-white", reduce ? "py-32" : "h-[220svh]")} aria-labelledby="sam-title">
      <div className={cn(!reduce && "sticky top-0 flex h-[100svh] flex-col justify-center overflow-hidden pt-[var(--fm-nav-h)]")}>
        <Container>
          <div className="grid grid-cols-12 items-end gap-y-3">
            <h2 id="sam-title" className="fm-title col-span-12 md:col-span-7">Every carton, segmented.</h2>
            <p className="fm-lede col-span-12 text-white/65 md:col-span-5 md:pb-1">
              sam-3.1 returns a mask and a track ID for each object. Python merges re-entries and counts what is left.
            </p>
          </div>
          <div className="relative mt-10 aspect-[16/9] max-h-[62svh] w-full overflow-hidden rounded-fm-xl bg-[#111] max-md:mt-8 max-md:aspect-[4/3] max-md:rounded-fm">
            <img src="/media/sam_raw.webp" alt="Test photo of cartons before segmentation" width={1448} height={1086} loading="lazy" decoding="async" className="absolute inset-0 h-full w-full object-cover object-[50%_28%]" />
            <img
              src="/media/sam_overlay.webp"
              alt="The same photo with sam-3.1 masks, boxes and track IDs drawn from the model's records"
              width={1448}
              height={1086}
              loading="lazy"
              decoding="async"
              className="absolute inset-0 h-full w-full object-cover object-[50%_28%]"
              style={{ clipPath: `inset(0 ${(1 - w) * 100}% 0 0)` }}
            />
            {!reduce && w > 0 && w < 1 && <span className="absolute inset-y-0 w-px bg-white/90" style={{ left: `${w * 100}%` }} aria-hidden />}
            <span className="absolute left-4 top-4 rounded-full bg-black/55 px-3 py-1 text-[12px] font-medium text-white backdrop-blur-md">{w < 0.5 ? "Raw photo" : "sam-3.1 masks + track IDs"}</span>
          </div>
          <p className="mt-4 text-center text-[12px] text-white/50">Real sam-3.1 output on a still test photo (scripts/smoke_models.py). Not a case frame.</p>
        </Container>
      </div>
    </section>
  );
}

/* ——— every delivery on camera ——— */
export function Deliveries({ cases }: { cases: CaseSummary[] }) {
  const onCamera = cases.filter((c) => c.scenario_id && SCENARIO_FRAMES[c.scenario_id]);
  if (onCamera.length === 0) return null;
  return (
    <section className="bg-fm-canvas pb-24 pt-32 max-md:pb-16 max-md:pt-24" aria-labelledby="deliveries-title">
      <Container>
        <Reveal as="h2" className="fm-title max-w-[16ch]"><span id="deliveries-title">Every delivery, on camera.</span></Reveal>
        <Reveal as="p" delay={80} className="fm-lede mt-5 max-w-[40ch] text-fm-muted">
          Each scenario is a real video run through the pipeline. The verdicts below are what the case API serves.
        </Reveal>
      </Container>
      <div className="mx-auto mt-14 max-w-[1200px] overflow-x-auto px-6 [scrollbar-width:none] max-md:snap-x max-md:snap-mandatory max-md:scroll-px-6">
        <ul className="grid grid-flow-col gap-6 max-md:auto-cols-[82%] md:grid-cols-4 md:grid-flow-row max-md:gap-4">
          {onCamera.map((c, i) => (
            <Reveal as="li" key={c.po_id} delay={i * 90} className="min-w-0 max-md:snap-start">
              <Link to={`/cases/${c.po_id}`} className="group block rounded-fm-xl">
                <div className="aspect-[16/10] overflow-hidden rounded-fm-xl bg-fm-tile">
                  <img src={SCENARIO_FRAMES[c.scenario_id!]} alt={`Dock frame from ${c.scenario_id}`} width={1280} height={720} loading="lazy" decoding="async" className="h-full w-full object-cover transition-transform duration-700 ease-[var(--fm-ease)] group-hover:scale-[1.03]" />
                </div>
                <div className="mt-5 flex items-center justify-between gap-3">
                  <StatusBadge verdict={c.verdict} />
                  {c.held_paise > 0 && <span className="font-mono text-[15px] font-medium text-fm-hold">{formatINR(c.held_paise)}</span>}
                </div>
                <p className="mt-3 text-[17px] font-semibold tracking-[-0.016em]">{c.discrepancy_types?.length ? typeLabel(c.discrepancy_types[0]) : "All four sources agree"}</p>
                <p className="mt-0.5 truncate text-[14px] text-fm-muted">{c.vendor_name}</p>
                <p className="mt-0.5 flex items-center gap-1 font-mono text-[12px] text-fm-faint">
                  {c.po_number} · {c.scenario_id}
                  <ArrowUpRight size={13} className="opacity-0 transition-opacity group-hover:opacity-100" aria-hidden />
                </p>
              </Link>
            </Reveal>
          ))}
        </ul>
      </div>
    </section>
  );
}

/* ——— how it decides ——— */
export function HowItWorks({ line, phrases }: { line: CaseLineRead; phrases: string[] }) {
  const rule = videoClause(line.cited_rules);
  const diff = line.observed_count !== null ? line.invoiced_qty - line.observed_count : null;
  const steps: { model: string; title: string; body: string; media: ReactNode }[] = [
    {
      model: "muse-spark-1.3",
      title: "Muse Spark watches the video.",
      body: "It reads the PO lines and chooses what to track, in a short noun phrase per line.",
      media: (
        <>
          <img src="/media/scn4_mixed_f2.webp" alt="Mixed delivery of cartons and sacks" width={1280} height={720} loading="lazy" decoding="async" className="absolute inset-0 h-full w-full object-cover" />
          <div className="absolute inset-x-4 bottom-4 flex flex-wrap gap-2">
            {phrases.map((ph) => <span key={ph} className="rounded-full bg-black/60 px-3 py-1 font-mono text-[12px] text-white backdrop-blur-md">“{ph}”</span>)}
          </div>
        </>
      ),
    },
    {
      model: "sam-3.1",
      title: "SAM 3.1 segments and tracks.",
      body: "Each object gets a mask and an ID across frames. Weak tracks are dropped, never guessed.",
      media: <img src="/media/sam_overlay.webp" alt="sam-3.1 masks and track IDs on cartons" width={1448} height={1086} loading="lazy" decoding="async" className="absolute inset-0 h-full w-full object-cover" />,
    },
    {
      model: "Python",
      title: "Python counts and reconciles.",
      body: "PO, GRN, invoice and vision side by side. The model never does arithmetic.",
      media: (
        <div className="absolute inset-0 flex flex-col items-center justify-center bg-fm-tile">
          <div className="fm-figure whitespace-nowrap text-[clamp(36px,3.6vw,52px)]">
            {line.invoiced_qty} − {line.observed_count ?? "—"} = <span className="text-fm-hold">{diff ?? "—"}</span>
          </div>
          <div className="mt-2 text-[13px] text-fm-muted">invoiced − seen on video</div>
        </div>
      ),
    },
    {
      model: "decision agent",
      title: "The agent applies your policy.",
      body: "Rules compiled from your own document. Every verdict cites the clause it rests on.",
      media: (
        <div className="absolute inset-0 flex flex-col justify-between bg-fm-tile p-6">
          <span className="fm-figure text-[52px] leading-none">§{rule?.source_clause ?? "—"}</span>
          <p className="line-clamp-4 text-[14px] leading-[1.5] text-fm-muted">“{rule ? excerpt(rule.source_text, 150) : ""}”</p>
        </div>
      ),
    },
  ];
  return (
    <section className="bg-fm-canvas pb-32 max-md:pb-24" aria-labelledby="how-title">
      <Container>
        <div className="border-t border-fm-border pt-24 max-md:pt-16">
          <Reveal as="h2" className="fm-title max-w-[14ch]"><span id="how-title">How it decides.</span></Reveal>
          <Reveal as="p" delay={80} className="fm-lede mt-5 max-w-[42ch] text-fm-muted">Two models see. Code counts. An agent decides, and weak evidence goes to a person instead of being approved.</Reveal>
        </div>
        <ol className="mt-16 grid grid-cols-12 gap-x-6 gap-y-14 max-md:mt-12">
          {steps.map((s, i) => (
            <Reveal as="li" key={s.title} delay={i * 90} className="col-span-12 sm:col-span-6 lg:col-span-3">
              <div className="relative aspect-[4/3] overflow-hidden rounded-fm">{s.media}</div>
              <p className="mt-6 font-mono text-[12px] text-fm-faint">{String(i + 1).padStart(2, "0")} · {s.model}</p>
              <h3 className="mt-2 text-[21px] font-semibold leading-[1.2] tracking-[-0.022em]">{s.title}</h3>
              <p className="mt-2 text-[15px] leading-[1.5] text-fm-muted">{s.body}</p>
            </Reveal>
          ))}
        </ol>
      </Container>
    </section>
  );
}

/* ——— built on Meta models ——— */
const MODELS = [
  { id: "muse-spark-1.3", line: "Watches the dock video, picks what to track, checks damage, and runs the decision agent." },
  { id: "sam-3.1", line: "Segments and tracks every object. The only source of counts." },
  { id: "muse-voice-transcribe-1.0", line: "Transcribes the storekeeper's voice remark. Context, never evidence." },
  { id: "muse-image-1.0", line: "Generates synthetic test scenes for evaluation only." },
  { id: "muse-spark-1.3-contributor", line: "Writes synthetic documents and summaries at lower cost." },
];

export function Models() {
  return (
    <section className="bg-fm-section py-32 max-md:py-24" aria-labelledby="models-title">
      <Container>
        <div className="grid grid-cols-12 gap-x-6 gap-y-14">
          <div className="col-span-12 lg:col-span-6">
            <Reveal as="h2" className="fm-title"><span id="models-title">Built on Meta models.</span></Reveal>
            <ul className="mt-12">
              {MODELS.map((m, i) => (
                <Reveal as="li" key={m.id} delay={i * 60} className="grid grid-cols-12 gap-x-4 gap-y-1 border-t border-fm-border py-5 last:border-b">
                  <span className="col-span-12 font-mono text-[14px] font-medium sm:col-span-6">{m.id}</span>
                  <span className="col-span-12 text-[15px] leading-[1.5] text-fm-muted sm:col-span-6">{m.line}</span>
                </Reveal>
              ))}
            </ul>
          </div>
          <Reveal delay={120} className="col-span-12 lg:col-span-6 lg:pt-3">
            <figure>
              <div className="relative aspect-[3/2] overflow-hidden rounded-fm-xl bg-fm-sunken">
                <img src="/media/synthetic_muse_image.webp" alt="Synthetic warehouse scene generated by muse-image-1.0" width={1600} height={1067} loading="lazy" decoding="async" className="h-full w-full object-cover" />
                <span className="absolute left-4 top-4 rounded-full bg-black/60 px-3 py-1 text-[12px] font-medium text-white backdrop-blur-md">Synthetic</span>
              </div>
              <figcaption className="mt-4 text-[14px] text-fm-muted">Synthetic — generated by Muse Image, used only for evaluation. Never evidence.</figcaption>
            </figure>
          </Reveal>
        </div>
      </Container>
    </section>
  );
}

/* ——— measured results ——— */
function Figure({ value, label, note, delay }: { value: string; label: string; note: string; delay: number }) {
  return (
    <Reveal delay={delay} className="col-span-6 border-t border-fm-border pt-6 lg:col-span-3">
      <div className="fm-figure text-[clamp(56px,6vw,88px)] leading-none">{value}</div>
      <p className="mt-4 text-[17px] font-semibold tracking-[-0.016em]">{label}</p>
      <p className="mt-1 text-[14px] text-fm-muted">{note}</p>
    </Reveal>
  );
}

export function Results({ results }: { results: EvalResults | null }) {
  const c = results?.videos.count_summary;
  const d = results?.videos.damage_summary;
  const agent = results?.verdicts.agent ?? null;
  const frac = (s?: { correct: number; measured: number } | null) => (s && s.measured > 0 ? `${s.correct}/${s.measured}` : "—");
  return (
    <section className="bg-fm-canvas py-32 max-md:py-24" aria-labelledby="results-title">
      <Container>
        <Reveal as="h2" className="fm-title"><span id="results-title">Measured, not claimed.</span></Reveal>
        <Reveal as="p" delay={80} className="fm-lede mt-5 max-w-[44ch] text-fm-muted">From the evaluation run against ground truth. Anything not measured yet shows a dash.</Reveal>
        <div className="mt-16 grid grid-cols-12 gap-x-6 gap-y-12">
          <Figure delay={0} value={frac(c)} label="Video count lines exact" note="SAM tracks vs true count, per line" />
          <Figure delay={80} value={frac(d)} label="Damage flags exact" note="Flagged vs truly damaged units" />
          <Figure delay={160} value={c?.mean_abs_error != null ? c.mean_abs_error.toFixed(1) : "—"} label="Mean count error" note="Units, across measured lines" />
          <Figure delay={240} value={agent?.accuracy != null ? `${Math.round(agent.accuracy * 100)}%` : "—"} label="Agent verdict accuracy" note={agent ? `${agent.cases_correct} of ${agent.cases_total} cases` : "Not measured yet"} />
        </div>
        <Reveal delay={120} className="mt-14">
          <Link to="/eval" className="inline-flex items-center gap-1 text-[17px] text-fm-accent-text hover:underline underline-offset-4">See the full evaluation <span aria-hidden>›</span></Link>
        </Reveal>
      </Container>
    </section>
  );
}

/* ——— closing call to action ——— */
export function Closing({ replayTo, caseTo }: { replayTo: string; caseTo: string }) {
  return (
    <section className="bg-fm-section py-32 text-center max-md:py-24">
      <Container>
        <Reveal as="h2" className="fm-display mx-auto max-w-[14ch]">Pay for what arrived.</Reveal>
        <Reveal delay={100} className="mt-10 flex flex-wrap items-center justify-center gap-4">
          <Link to={replayTo} className="inline-flex h-12 items-center rounded-full bg-fm-accent px-6 text-[17px] font-medium text-white transition-colors hover:bg-fm-accent-hover">Watch it decide</Link>
          <Link to={caseTo} className="inline-flex h-12 items-center gap-1 px-2 text-[17px] text-fm-accent-text hover:underline underline-offset-4">Open the case <span aria-hidden>›</span></Link>
        </Reveal>
      </Container>
    </section>
  );
}

