/** Landing: the 20-second pitch. Real scn2 footage, the four-way match resolving live,
 *  and the money held. Every figure is fetched from the API, nothing is typed in. */
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { EvidenceVideo } from "../components/evidence/EvidenceVideo";
import { Wordmark } from "../components/shell/BrandMark";
import { Button } from "../components/ui/Button";
import { FourMatchStrip } from "../components/ui/FourMatch";
import { useCountUp } from "../components/ui/LiveCounter";
import { StatusBadge } from "../components/ui/StatusBadge";
import { Kbd, Tag } from "../components/ui/Tag";
import { api } from "../lib/api";
import { cn } from "../lib/cn";
import { formatINR } from "../lib/format";
import { useTheme } from "../lib/theme";

const STEPS = [
  { n: "01", model: "muse-spark-1.3", title: "Watches the dock", body: "Reads the receiving video against the PO lines and decides exactly what to look for: “cardboard box”, “white sack”." },
  { n: "02", model: "sam-3.1", title: "Tracks every unit", body: "Segments and tracks each object across frames. Re-entries are merged in Python; weak tracks are dropped." },
  { n: "03", model: "python", title: "Reconciles four ways", body: "PO, GRN, invoice and vision side by side. Variance and rupees are computed in code, never by the model." },
  { n: "04", model: "decision agent", title: "Holds the payment", body: "Applies your compiled policy, cites the clause, drafts the debit note and seals a SHA-256 evidence pack." },
];

export function Landing() {
  const { theme, toggle } = useTheme();
  const cases = useQuery({ queryKey: ["cases"], queryFn: api.cases });
  const hero = cases.data?.find((c) => c.scenario_id === "scn2_short") ?? cases.data?.find((c) => c.evidence_source === "video");
  const detail = useQuery({ queryKey: ["case", hero?.po_id], queryFn: () => api.case(hero!.po_id), enabled: !!hero });
  const line = detail.data?.lines[0];
  const [phase, setPhase] = useState<"idle" | "counting" | "settled">("idle");

  useEffect(() => {
    if (!line) return;
    const a = setTimeout(() => setPhase("counting"), 900);
    const b = setTimeout(() => setPhase("settled"), 900 + 2300);
    return () => { clearTimeout(a); clearTimeout(b); };
  }, [line]);

  const observed = line?.observed_count ?? 0;
  const count = useCountUp(observed, phase === "counting", 2100);
  const visionValue = phase === "idle" ? null : phase === "counting" ? count : observed;
  const totals = cases.data ? {
    held: cases.data.reduce((s, c) => s + c.held_paise, 0),
    n: cases.data.length,
    flagged: cases.data.filter((c) => c.verdict && c.verdict !== "approve").length,
  } : null;

  return (
    <div className="fm-scroll h-full overflow-auto bg-fm-bg">
      <header className="sticky top-0 z-20 border-b border-fm-border bg-fm-bg/90 backdrop-blur-[2px]">
        <div className="mx-auto flex h-12 max-w-[1280px] items-center gap-3 px-5">
          <Wordmark />
          <span className="inline-flex h-5 items-center rounded-fm-sm border border-dashed border-fm-hold-line px-1.5 font-cond text-[10px] font-semibold uppercase tracking-[0.08em] text-fm-hold">Synthetic data</span>
          <nav className="ml-auto flex items-center gap-1">
            <Link to="/eval" className="hidden rounded-fm-sm px-2.5 py-1.5 text-[12.5px] text-fm-muted hover:text-fm-text sm:block">Eval</Link>
            <Link to="/policy" className="hidden rounded-fm-sm px-2.5 py-1.5 text-[12.5px] text-fm-muted hover:text-fm-text sm:block">Policy</Link>
            <button type="button" onClick={toggle} aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"} className="rounded-fm-sm p-2 text-fm-muted hover:text-fm-text">
              {theme === "dark" ? <Sun size={15} /> : <Moon size={15} />}
            </button>
            <Button asChild variant="primary" size="sm"><Link to="/dock">Open console <ArrowRight size={13} /></Link></Button>
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-[1280px] px-5">
        {/* ——— hero ——— */}
        <section className="grid items-center gap-10 py-12 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)] lg:py-16">
          <div className="min-w-0">
            <div className="fm-label mb-5 flex items-center gap-2">
              <span className="h-px w-6 bg-fm-hold" />Procurement payment control
            </div>
            <h1 className="text-[44px] font-semibold leading-[1.02] tracking-[-0.035em] sm:text-[60px]">
              {line ? <>Paper said <span className="font-mono font-medium tracking-[-0.05em]">{line.invoiced_qty}</span>.<br />The truck had <span className="font-mono font-medium tracking-[-0.05em] text-fm-hold">{line.observed_count}</span>.</> : <>Paper says one thing.<br />The truck says another.</>}
            </h1>
            <p className="mt-6 max-w-[520px] text-[16px] leading-relaxed text-fm-muted">
              Companies pay for goods nobody verified. FourthMatch makes the delivery itself the fourth match: it watches the receiving-dock video, reconciles it against the PO, GRN and invoice, and holds the payment, citing your own policy.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-2">
              <Button asChild variant="accent" size="lg"><Link to={hero ? `/dock?replay=${hero.po_id}` : "/dock"}>Watch it decide <ArrowRight size={15} /></Link></Button>
              <Button asChild variant="secondary" size="lg"><Link to={hero ? `/cases/${hero.po_id}` : "/cases"}>Open the evidence</Link></Button>
            </div>
            <p className="mt-4 flex items-center gap-1.5 text-[11.5px] text-fm-faint">Press <Kbd>⌘K</Kbd> anywhere in the console to jump to a PO, vendor or clause.</p>
          </div>

          <div className="min-w-0">
            <div className="rounded-fm border border-fm-border bg-fm-panel p-3">
              <div className="mb-3 flex items-center justify-between px-0.5">
                <span className="fm-label flex items-center gap-2">
                  <span className="fm-live-dot h-1.5 w-1.5 rounded-full bg-fm-fraud" />
                  {detail.data ? `${detail.data.po_number} · ${detail.data.vendor_name}` : "Receiving dock"}
                </span>
                {detail.data?.scenario_id && <Tag>{detail.data.scenario_id}</Tag>}
              </div>
              {detail.data?.video_url ? (
                <EvidenceVideo
                  src={detail.data.video_url}
                  phrase={line?.perception?.noun_phrase}
                  count={visionValue}
                  countLabel={phase === "settled" ? "Unique tracks" : "Tracking"}
                  scanning={phase === "counting"}
                  camera="DOCK-01 · CAM 2"
                />
              ) : (
                <div className="fm-dotgrid aspect-video rounded-fm border border-fm-border bg-fm-sunken" />
              )}
              {line && (
                <FourMatchStrip
                  className="mt-3"
                  size="lg"
                  values={{ po: line.po_qty, grn: line.grn_qty, invoice: line.invoiced_qty, vision: visionValue }}
                  unit={line.unit}
                  live={phase === "counting"}
                  visionPending={phase === "idle"}
                  variancePct={phase === "settled" ? line.variance_pct : null}
                  sub={{ po: "purchase order", grn: phase === "settled" && line.grn_qty !== line.observed_count ? <span className="text-fm-hold">contradicted · §8.4</span> : "storekeeper signed", invoice: "vendor invoice", vision: phase === "counting" ? "counting…" : "dock video" }}
                />
              )}
              <div className={cn("mt-3 flex flex-wrap items-center justify-between gap-3 rounded-fm border px-4 py-3 transition-opacity duration-300",
                phase === "settled" ? "border-fm-hold-line bg-fm-hold-bg opacity-100" : "border-fm-border opacity-40")}>
                <div className="flex items-center gap-3">
                  <StatusBadge verdict={phase === "settled" ? detail.data?.verdict ?? null : null} label={phase === "settled" ? undefined : "Deciding"} />
                  <span className="text-[12.5px] text-fm-muted">{phase === "settled" ? `Clauses ${detail.data?.clauses?.map((c) => `§${c}`).join(" · ")}` : "Decision agent waiting on vision"}</span>
                </div>
                <span className="font-mono text-[22px] font-medium tracking-[-0.03em] text-fm-hold">
                  {phase === "settled" && detail.data ? `${formatINR(detail.data.held_paise)} held` : "₹—"}
                </span>
              </div>
            </div>
          </div>
        </section>

        {/* ——— proof row ——— */}
        {totals && (
          <section className="grid grid-cols-2 divide-fm-border border-y border-fm-border md:grid-cols-4 md:divide-x" aria-label="Demo dataset">
            {[
              { k: "Cases decided", v: String(totals.n) },
              { k: "Payments stopped", v: String(totals.flagged) },
              { k: "Rupees held", v: formatINR(totals.held) },
              { k: "Numbers from the LLM", v: "0" },
            ].map((x) => (
              <div key={x.k} className="px-5 py-6">
                <div className="fm-label">{x.k}</div>
                <div className="mt-2 font-mono text-[30px] font-medium tracking-[-0.04em]">{x.v}</div>
              </div>
            ))}
          </section>
        )}

        {/* ——— how it works ——— */}
        <section className="py-14">
          <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
            <h2 className="max-w-xl text-[28px] font-semibold leading-tight tracking-[-0.025em]">An agent that decides whether a payment goes out. Not a box counter.</h2>
            <p className="max-w-sm text-[13px] text-fm-muted">Weak evidence never approves a payment: it routes to a human. Every decision is re-verifiable from a hash-sealed evidence pack.</p>
          </div>
          <ol className="grid gap-px overflow-hidden rounded-fm border border-fm-border bg-fm-border md:grid-cols-4">
            {STEPS.map((s) => (
              <li key={s.n} className="flex flex-col gap-3 bg-fm-panel p-5">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-[12px] text-fm-hold">{s.n}</span>
                  <Tag>{s.model}</Tag>
                </div>
                <h3 className="text-[15px] font-semibold tracking-[-0.01em]">{s.title}</h3>
                <p className="text-[12.5px] leading-relaxed text-fm-muted">{s.body}</p>
              </li>
            ))}
          </ol>
        </section>
      </main>

      <footer className="border-t border-fm-border">
        <div className="mx-auto flex max-w-[1280px] flex-wrap items-center justify-between gap-3 px-5 py-5 text-[11.5px] text-fm-faint">
          <span>Built Oct 30 – Nov 4, 2026 for the Meta Global AI Hackathon. All vendors, documents and footage are synthetic.</span>
          <span className="font-mono">muse-spark-1.3 · sam-3.1 · muse-voice-transcribe-1.0 · muse-image-1.0</span>
        </div>
      </footer>
    </div>
  );
}
