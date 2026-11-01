import { Pause, Play } from "lucide-react";
import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";
import { cn } from "../../lib/cn";
import { LiveCounter } from "../ui/LiveCounter";

const FPS = 24;

export interface EvidenceVideoHandle { seek: (t: number) => void; play: () => void }

interface Props {
  src: string;
  poster?: string;
  phrase?: string | null;
  /** Object count to show over the footage (from SAM tracks). null hides it. */
  count?: number | null;
  countLabel?: string;
  /** A model is working on the footage right now. */
  scanning?: boolean;
  autoPlay?: boolean;
  loop?: boolean;
  camera?: string;
  className?: string;
}

function tc(t: number) {
  const m = Math.floor(t / 60);
  const s = Math.floor(t % 60);
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

const pill = "rounded-full bg-black/45 px-3 py-1.5 text-[12px] font-medium text-white backdrop-blur-md";

/** Dock-camera player as a large rounded media card: camera + timecode, the SAM phrase,
 *  the track count, and a quiet scrubber underneath. */
export const EvidenceVideo = forwardRef<EvidenceVideoHandle, Props>(function EvidenceVideo(
  { src, poster, phrase, count, countLabel = "Unique tracks", scanning, autoPlay = true, loop = true, camera = "Dock 01 · Camera 2", className }, ref,
) {
  const v = useRef<HTMLVideoElement>(null);
  const [t, setT] = useState(0);
  const [dur, setDur] = useState(0);
  const [playing, setPlaying] = useState(autoPlay);

  useImperativeHandle(ref, () => ({
    seek: (time: number) => { if (v.current) { v.current.currentTime = time; v.current.pause(); } },
    play: () => { void v.current?.play(); },
  }));

  useEffect(() => {
    const el = v.current;
    if (!el) return;
    let raf = 0;
    let last = -1;
    const loopFn = () => {
      const now = Math.floor(el.currentTime * FPS);
      if (now !== last) { last = now; setT(el.currentTime); }
      raf = requestAnimationFrame(loopFn);
    };
    raf = requestAnimationFrame(loopFn);
    return () => cancelAnimationFrame(raf);
  }, []);

  const toggle = useCallback(() => {
    const el = v.current;
    if (!el) return;
    if (el.paused) void el.play(); else el.pause();
  }, []);

  const pct = dur ? (t / dur) * 100 : 0;

  return (
    <div className={cn("group relative overflow-hidden rounded-fm-xl bg-black text-white max-sm:rounded-fm", className)}>
      <div className="relative aspect-video w-full">
        <video
          ref={v}
          src={src}
          poster={poster}
          muted
          playsInline
          autoPlay={autoPlay}
          loop={loop}
          preload="auto"
          onLoadedMetadata={(e) => setDur(e.currentTarget.duration)}
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          onClick={toggle}
          className="absolute inset-0 h-full w-full cursor-pointer object-cover"
          aria-label="Receiving-dock video"
        />
        <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(180deg,rgba(0,0,0,0.28)_0%,rgba(0,0,0,0)_22%,rgba(0,0,0,0)_62%,rgba(0,0,0,0.42)_100%)]" aria-hidden />
        <div className="pointer-events-none absolute inset-x-0 top-0 flex items-start justify-between gap-3 p-4 max-sm:p-3">
          <span className={cn(pill, "flex items-center gap-2")}>
            <span className={cn("h-2 w-2 rounded-full bg-[#ff453a]", playing && "fm-live-dot")} aria-hidden />
            {camera}
          </span>
          <span className={cn(pill, "font-mono tabular-nums max-sm:hidden")}>{tc(t)}</span>
        </div>
        <div className="pointer-events-none absolute inset-x-0 bottom-0 flex items-end justify-between gap-3 p-4 max-sm:p-3">
          {phrase ? (
            <span className={cn(pill, "flex min-w-0 items-center gap-2")}>
              {scanning && <span className="fm-live-dot h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--fm-amber-fixed)]" aria-hidden />}
              <span className="text-white/60">sam-3.1</span>
              <span className="truncate">“{phrase}”</span>
            </span>
          ) : scanning ? (
            <span className={cn(pill, "flex items-center gap-2")}><span className="fm-live-dot h-1.5 w-1.5 rounded-full bg-[var(--fm-amber-fixed)]" aria-hidden />Watching the footage</span>
          ) : <span />}
          {count != null && (
            <span className="flex shrink-0 flex-col items-end rounded-[18px] bg-black/45 px-4 py-2.5 backdrop-blur-md max-sm:px-3 max-sm:py-2">
              <span className="text-[12px] font-medium text-white/70">{countLabel}</span>
              <LiveCounter value={count} label={countLabel} className="text-[40px] max-sm:text-[28px]" />
            </span>
          )}
        </div>
      </div>
      <div className="flex items-center gap-3 px-4 py-3 max-sm:px-3 [:root[data-theme=dark]_&]:bg-[#161617]">
        <button type="button" onClick={toggle} aria-label={playing ? "Pause" : "Play"} className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-white/10 text-white transition-colors hover:bg-white/20">
          {playing ? <Pause size={14} fill="currentColor" /> : <Play size={14} fill="currentColor" className="translate-x-px" />}
        </button>
        <div className="relative h-6 flex-1">
          <input
            type="range"
            min={0}
            max={dur || 1}
            step={1 / FPS}
            value={t}
            onChange={(e) => { if (v.current) v.current.currentTime = Number(e.target.value); }}
            aria-label="Scrub video"
            className="absolute inset-0 z-10 w-full cursor-pointer opacity-0"
          />
          <div className="absolute inset-x-0 top-1/2 h-1 -translate-y-1/2 rounded-full bg-white/15" />
          <div className="absolute left-0 top-1/2 h-1 -translate-y-1/2 rounded-full bg-white" style={{ width: `${pct}%` }} />
          <div className="absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-white opacity-0 transition-opacity group-hover:opacity-100" style={{ left: `${pct}%` }} />
        </div>
        <span className="shrink-0 font-mono text-[12px] tabular-nums text-white/60">{tc(t)} / {tc(dur)}</span>
      </div>
    </div>
  );
});
