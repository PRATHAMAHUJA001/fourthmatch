import { Pause, Play } from "lucide-react";
import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";
import { cn } from "../../lib/cn";

const FPS = 24;

export interface EvidenceVideoHandle { seek: (t: number) => void; play: () => void }

interface Props {
  src: string;
  phrase?: string | null;
  /** Object count to show in the HUD (from SAM tracks). null hides it. */
  count?: number | null;
  countLabel?: string;
  scanning?: boolean;
  autoPlay?: boolean;
  loop?: boolean;
  camera?: string;
  className?: string;
  compact?: boolean;
}

function tc(t: number) {
  const m = Math.floor(t / 60);
  const s = Math.floor(t % 60);
  const f = Math.floor((t % 1) * FPS);
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}:${String(f).padStart(2, "0")}`;
}

/** Dock-camera player: viewfinder ticks, timecode + frame HUD, SAM phrase, object counter, scrubber. */
export const EvidenceVideo = forwardRef<EvidenceVideoHandle, Props>(function EvidenceVideo(
  { src, phrase, count, countLabel = "Objects", scanning, autoPlay = true, loop = true, camera = "DOCK-01 · CAM 2", className, compact }, ref,
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
    const loopFn = () => { setT(el.currentTime); raf = requestAnimationFrame(loopFn); };
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
    <div className={cn("group relative overflow-hidden rounded-fm border border-fm-border bg-black", className)}>
      <div className="relative aspect-video w-full">
        <video
          ref={v}
          src={src}
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
        {/* viewfinder ticks */}
        <div className="pointer-events-none absolute inset-3 fm-ticks [--fm-tick:rgba(255,255,255,0.55)]" aria-hidden />
        {scanning && <div className="pointer-events-none absolute inset-0" aria-hidden><div className="fm-scanline" /></div>}
        {/* HUD */}
        <div className="pointer-events-none absolute inset-x-0 top-0 flex items-start justify-between p-4 font-mono text-[10.5px] text-white/85">
          <span className="flex items-center gap-1.5 rounded-[2px] bg-black/55 px-1.5 py-0.5">
            <span className={cn("h-1.5 w-1.5 rounded-full bg-[#ff4d4f]", playing && "fm-live-dot")} />
            {camera}
          </span>
          <span className="rounded-[2px] bg-black/55 px-1.5 py-0.5 tabular-nums">
            {tc(t)} <span className="text-white/50">· F{String(Math.floor(t * FPS)).padStart(4, "0")}</span>
          </span>
        </div>
        <div className="pointer-events-none absolute inset-x-0 bottom-0 flex items-end justify-between p-4 font-mono text-white">
          {phrase ? (
            <span className="rounded-[2px] bg-black/60 px-1.5 py-1 text-[10.5px] text-white/85">
              sam-3.1 <span className="text-white/45">›</span> <span className="text-[#ffb224]">"{phrase}"</span>
            </span>
          ) : <span />}
          {count != null && (
            <span className={cn("flex flex-col items-end rounded-[2px] bg-black/60 px-2 py-1", compact && "scale-90 origin-bottom-right")}>
              <span className="font-cond text-[9.5px] font-semibold uppercase tracking-[0.1em] text-white/60">{countLabel}</span>
              <span className="text-[26px] font-medium leading-none tabular-nums">{String(count).padStart(2, "0")}</span>
            </span>
          )}
        </div>
      </div>
      {/* scrubber */}
      <div className="flex items-center gap-2 border-t border-white/10 bg-[#0d0e10] px-2 py-1.5">
        <button type="button" onClick={toggle} aria-label={playing ? "Pause" : "Play"} className="flex h-6 w-6 items-center justify-center rounded-[3px] text-white/80 hover:bg-white/10">
          {playing ? <Pause size={13} /> : <Play size={13} />}
        </button>
        <div className="relative h-5 flex-1">
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
          <div className="absolute inset-x-0 top-1/2 h-[3px] -translate-y-1/2 rounded-full bg-white/12" />
          <div className="absolute left-0 top-1/2 h-[3px] -translate-y-1/2 rounded-full bg-[#ffb224]" style={{ width: `${pct}%` }} />
          {Array.from({ length: 11 }, (_, i) => (
            <span key={i} className="absolute top-[3px] h-[3px] w-px bg-white/25" style={{ left: `${i * 10}%` }} aria-hidden />
          ))}
          <div className="absolute top-1/2 h-3 w-[3px] -translate-x-1/2 -translate-y-1/2 rounded-[1px] bg-white" style={{ left: `${pct}%` }} />
        </div>
        <span className="w-[86px] text-right font-mono text-[10.5px] tabular-nums text-white/60">{tc(t)}</span>
      </div>
    </div>
  );
});
