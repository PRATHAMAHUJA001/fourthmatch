/** Landing: an Apple-style product page. Real dock footage, then a scroll-linked story of one
 *  delivery (scn2_short) where paper says one number and the camera another. Every figure is
 *  fetched from the API (or the MSW dataset built from repo data files); nothing is typed in. */
import { useQuery } from "@tanstack/react-query";
import { useRef } from "react";
import { Link } from "react-router-dom";
import { CommandPalette } from "../components/shell/CommandPalette";
import { TopNav } from "../components/shell/TopNav";
import { useGlobalKeys } from "../components/shell/useGlobalKeys";
import { Skeleton } from "../components/ui/EmptyState";
import { api } from "../lib/api";
import { useReducedMotion, useScrollFrame } from "../lib/motion";
import { SCENARIO_FRAMES } from "./landing/content";
import { Closing, Deliveries, HowItWorks, Models, Results, SamReveal } from "./landing/Sections";
import { Story } from "./landing/Story";

const REPO = "https://github.com/PRATHAMAHUJA001/fourthmatch#readme";

function Hero({ replayTo, caseTo }: { replayTo: string; caseTo: string }) {
  const reduce = useReducedMotion();
  const media = useRef<HTMLDivElement>(null);
  const copy = useRef<HTMLDivElement>(null);
  useScrollFrame((y) => {
    const vh = window.innerHeight || 1;
    if (media.current) media.current.style.transform = `translate3d(0, ${y * 0.28}px, 0) scale(${1 + Math.min(y / vh, 1) * 0.06})`;
    if (copy.current) {
      copy.current.style.opacity = String(Math.max(0, 1 - y / (vh * 0.55)));
      copy.current.style.transform = `translate3d(0, ${y * -0.12}px, 0)`;
    }
  }, !reduce);

  return (
    <section data-nav-dark className="relative h-[100svh] min-h-[600px] overflow-hidden bg-black text-white" aria-labelledby="hero-title">
      <div ref={media} className="absolute inset-0 will-change-transform">
        <video
          className="h-full w-full object-cover"
          autoPlay={!reduce}
          muted
          loop
          playsInline
          preload="auto"
          poster="/media/hero_poster.webp"
          aria-hidden
          tabIndex={-1}
        >
          <source src="/media/hero_loop.webm" type="video/webm" />
          <source src="/media/hero_loop.mp4" type="video/mp4" />
        </video>
      </div>
      <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(0,0,0,0.42)_0%,rgba(0,0,0,0)_22%)]" aria-hidden />
      <div className="absolute inset-0 bg-[linear-gradient(20deg,rgba(0,0,0,0.86)_0%,rgba(0,0,0,0.55)_38%,rgba(0,0,0,0.08)_70%,rgba(0,0,0,0)_100%)]" aria-hidden />
      <div ref={copy} className="relative mx-auto flex h-full max-w-[1200px] flex-col justify-end px-6 pb-[13svh] will-change-transform max-md:pb-[10svh]">
        <h1 id="hero-title" className="fm-hero max-w-[11ch] max-sm:max-w-none">The delivery is the fourth match.</h1>
        <p className="fm-lede mt-6 max-w-[40ch] text-white/85">
          FourthMatch holds procurement payments when the dock video contradicts the PO, GRN and invoice — and cites your own policy.
        </p>
        <div className="mt-10 flex flex-wrap items-center gap-x-6 gap-y-4">
          <Link to={replayTo} className="inline-flex h-12 items-center rounded-full bg-fm-accent px-6 text-[17px] font-medium text-white transition-colors duration-200 hover:bg-fm-accent-hover focus-visible:outline-white">
            Watch it decide
          </Link>
          <Link to={caseTo} className="inline-flex h-12 items-center gap-1 text-[17px] text-white hover:underline underline-offset-4 focus-visible:outline-white">
            Open a case <span aria-hidden>›</span>
          </Link>
        </div>
      </div>
      <p className="absolute bottom-5 right-6 text-[12px] text-white/55 max-sm:hidden">Receiving dock, scn2_short. Synthetic footage.</p>
    </section>
  );
}

export function Landing() {
  const [palette, setPalette] = useGlobalKeys();
  const cases = useQuery({ queryKey: ["cases"], queryFn: api.cases });
  const hero = cases.data?.find((c) => c.scenario_id === "scn2_short") ?? cases.data?.find((c) => c.evidence_source === "video");
  const detail = useQuery({ queryKey: ["case", hero?.po_id], queryFn: () => api.case(hero!.po_id), enabled: !!hero });
  const mixed = cases.data?.find((c) => c.scenario_id === "scn4_mixed");
  const mixedDetail = useQuery({ queryKey: ["case", mixed?.po_id], queryFn: () => api.case(mixed!.po_id), enabled: !!mixed });
  const evalq = useQuery({ queryKey: ["eval"], queryFn: api.eval });

  const line = detail.data?.lines.find((l) => l.evidence_source === "video") ?? detail.data?.lines[0];
  const replayTo = hero ? `/dock?replay=${hero.po_id}` : "/dock";
  const caseTo = hero ? `/cases/${hero.po_id}` : "/cases";
  const phrases = (mixedDetail.data?.lines ?? []).map((l) => l.perception?.noun_phrase).filter((x): x is string => !!x);
  const frame = (detail.data?.scenario_id && SCENARIO_FRAMES[detail.data.scenario_id]) || "/media/hero_poster.webp";

  return (
    <div className="min-h-screen bg-fm-canvas text-fm-text">
      <TopNav overlay onOpenPalette={() => setPalette(true)} />
      <main>
        <Hero replayTo={replayTo} caseTo={caseTo} />
        {detail.data && line ? (
          <Story detail={detail.data} line={line} frame={frame} />
        ) : (
          <div className="mx-auto flex h-[100svh] max-w-[1200px] flex-col items-center justify-center gap-6 px-6" role="status" aria-label="Loading the case">
            <Skeleton className="h-20 w-2/3" />
            <Skeleton className="h-40 w-full" />
          </div>
        )}
        <SamReveal />
        {cases.data && <Deliveries cases={cases.data} />}
        {line && <HowItWorks line={line} phrases={phrases} />}
        <Models />
        <Results results={evalq.data?.results ?? null} />
        <Closing replayTo={replayTo} caseTo={caseTo} />
      </main>
      <footer className="bg-fm-section">
        <div className="mx-auto flex max-w-[1200px] flex-wrap items-baseline justify-between gap-x-8 gap-y-3 border-t border-fm-border px-6 py-8 text-[12px] text-fm-muted">
          <p><span className="font-semibold text-fm-text">All data is synthetic.</span> Vendors, documents and footage were made for this demo. Built Oct 30 – Nov 4, 2026 for the Meta Global AI Hackathon.</p>
          <a href={REPO} className="text-fm-accent-text hover:underline underline-offset-4" target="_blank" rel="noreferrer">README on GitHub ›</a>
        </div>
      </footer>
      <CommandPalette open={palette} onOpenChange={setPalette} />
    </div>
  );
}
