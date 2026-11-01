import { useEffect, useState } from "react";
import { cn } from "../../lib/cn";

/** Pulls N real frames out of the evidence video in the browser (canvas), so the strip is
 *  always the actual footage. Clicking a frame seeks the player. */
export function Filmstrip({ src, frames = 6, onSelect, className }: { src: string; frames?: number; onSelect?: (t: number) => void; className?: string }) {
  const [shots, setShots] = useState<{ t: number; url: string }[]>([]);
  const [active, setActive] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    const video = document.createElement("video");
    video.src = src;
    video.muted = true;
    video.preload = "auto";
    video.crossOrigin = "anonymous";
    const canvas = document.createElement("canvas");
    const out: { t: number; url: string }[] = [];
    const grab = (i: number, times: number[]) => {
      if (cancelled || i >= times.length) { if (!cancelled) setShots([...out]); return; }
      video.currentTime = times[i];
      video.onseeked = () => {
        canvas.width = 240;
        canvas.height = Math.round((240 * video.videoHeight) / video.videoWidth) || 135;
        canvas.getContext("2d")?.drawImage(video, 0, 0, canvas.width, canvas.height);
        try { out.push({ t: times[i], url: canvas.toDataURL("image/jpeg", 0.72) }); } catch { /* tainted */ }
        setShots([...out]);
        grab(i + 1, times);
      };
    };
    video.onloadedmetadata = () => {
      const d = video.duration || 10;
      const times = Array.from({ length: frames }, (_, i) => Math.min(d - 0.05, (d * (i + 0.5)) / frames));
      grab(0, times);
    };
    return () => { cancelled = true; video.removeAttribute("src"); video.load(); };
  }, [src, frames]);

  return (
    <div className={cn("grid grid-cols-3 gap-2 sm:grid-cols-6", className)}>
      {Array.from({ length: frames }, (_, i) => {
        const s = shots[i];
        return (
          <button
            key={i}
            type="button"
            disabled={!s}
            onClick={() => { if (s) { setActive(i); onSelect?.(s.t); } }}
            className={cn(
              "group relative aspect-video overflow-hidden rounded-[12px] bg-fm-raised transition-[box-shadow,opacity] duration-200",
              active === i ? "shadow-[0_0_0_2px_var(--fm-panel),0_0_0_4px_var(--fm-accent)]" : "hover:opacity-90",
            )}
            aria-label={s ? `Jump to ${s.t.toFixed(1)} seconds` : "Loading frame"}
          >
            {s ? <img src={s.url} alt="" className="h-full w-full object-cover" /> : <span className="fm-skeleton absolute inset-0 rounded-none" />}
            {s && (
              <span className="absolute bottom-1.5 left-1.5 rounded-full bg-black/50 px-1.5 py-0.5 font-mono text-[10.5px] text-white backdrop-blur-sm">
                {s.t.toFixed(1)}s
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
