import * as Dialog from "@radix-ui/react-dialog";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Check, Film, Mic, RotateCcw, Square, Trash2, Upload, X } from "lucide-react";
import { useState, type ReactNode } from "react";
import { api } from "../../lib/api";
import { cn } from "../../lib/cn";
import { IS_MOCK } from "../../lib/demo";
import { formatINR } from "../../lib/format";
import { frameFor } from "../../lib/media";
import { formatClock, useVoiceRecorder } from "../../lib/useVoiceRecorder";
import { Button } from "../ui/Button";

function Step({ n, title, hint, children }: { n: number; title: string; hint?: string; children: ReactNode }) {
  return (
    <section>
      <h3 className="flex items-baseline gap-2 text-[17px] font-semibold tracking-[-0.016em]">
        <span className="text-fm-faint">{n}</span>{title}
        {hint && <span className="text-[13px] font-normal text-fm-faint">{hint}</span>}
      </h3>
      <div className="mt-3">{children}</div>
    </section>
  );
}

/** Pick a PO, drop the dock video, optionally record a remark, start the pipeline.
 *  A centred sheet on desktop, a bottom sheet on phones. */
export function NewDeliveryDialog({ open, onOpenChange, onStarted }: {
  open: boolean; onOpenChange: (o: boolean) => void; onStarted: (deliveryId: number, poId: number) => void;
}) {
  const pos = useQuery({ queryKey: ["purchase-orders"], queryFn: api.purchaseOrders, enabled: open });
  const [poId, setPoId] = useState<number | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [drag, setDrag] = useState(false);
  const voice = useVoiceRecorder();
  const create = useMutation({
    mutationFn: () => api.createDelivery(poId!, file, voice.file),
    onSuccess: (r) => { onStarted(r.delivery_id, poId!); onOpenChange(false); setFile(null); voice.remove(); },
  });
  const videoPos = (pos.data ?? []).filter((p) => p.scenario_id);
  const selected = videoPos.find((p) => p.id === poId);
  const needsFile = !IS_MOCK;

  return (
    <Dialog.Root open={open} onOpenChange={(o) => { if (!o) voice.remove(); onOpenChange(o); }}>
      <Dialog.Portal>
        <Dialog.Overlay className="fm-overlay fixed inset-0 z-50 bg-black/35 backdrop-blur-[6px]" />
        <Dialog.Content onOpenAutoFocus={(e) => { e.preventDefault(); (e.currentTarget as HTMLElement).focus(); }} className="fm-sheet fixed z-50 outline-none flex max-h-[min(860px,92vh)] flex-col overflow-hidden bg-fm-panel shadow-fm-float max-sm:inset-x-0 max-sm:bottom-0 max-sm:max-h-[92vh] max-sm:rounded-t-[28px] sm:left-1/2 sm:top-1/2 sm:w-[min(640px,calc(100vw-48px))] sm:-translate-x-1/2 sm:-translate-y-1/2 sm:rounded-fm-xl">
          <div className="mx-auto mt-2.5 h-1.5 w-10 shrink-0 rounded-full bg-fm-hover sm:hidden" aria-hidden />
          <div className="flex shrink-0 items-start justify-between gap-4 px-8 pb-2 pt-7 max-sm:px-5 max-sm:pt-4">
            <div>
              <Dialog.Title className="text-[28px] font-bold leading-tight tracking-[-0.03em]">New delivery</Dialog.Title>
              <Dialog.Description className="mt-1.5 max-w-[48ch] text-[15px] leading-snug text-fm-muted">
                Choose the purchase order this truck delivers against, then attach the dock video.
              </Dialog.Description>
            </div>
            <Dialog.Close className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-fm-raised text-fm-muted transition-colors hover:bg-fm-hover hover:text-fm-text" aria-label="Close"><X size={16} /></Dialog.Close>
          </div>

          <div className="fm-scroll flex min-h-0 flex-col gap-8 overflow-y-auto px-8 py-6 max-sm:px-5">
            <Step n={1} title="Purchase order">
              <div className="flex flex-col gap-2" role="radiogroup" aria-label="Purchase order">
                {pos.isLoading && <div className="fm-skeleton h-40 rounded-fm" />}
                {videoPos.map((p) => {
                  const on = poId === p.id;
                  const frame = frameFor(p.scenario_id);
                  return (
                    <button
                      key={p.id}
                      type="button"
                      role="radio"
                      aria-checked={on}
                      onClick={() => setPoId(p.id)}
                      className={cn("flex items-center gap-4 rounded-[16px] p-2.5 pr-4 text-left transition-[background-color,box-shadow] duration-200",
                        on ? "bg-fm-panel shadow-[inset_0_0_0_2px_var(--fm-accent)]" : "bg-fm-raised hover:bg-fm-hover")}
                    >
                      <span className="block h-12 w-[76px] shrink-0 overflow-hidden rounded-[10px] bg-fm-hover">
                        {frame && <img src={frame} alt="" width={1280} height={720} className="h-full w-full object-cover" />}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[15px] font-semibold tracking-[-0.012em]">{p.vendor_name}</span>
                        <span className="mt-0.5 block truncate text-[13px] text-fm-muted"><span className="font-mono text-[12.5px]">{p.po_number}</span> · {formatINR(p.total_paise)}</span>
                      </span>
                      <span className={cn("flex h-6 w-6 shrink-0 items-center justify-center rounded-full transition-colors", on ? "bg-fm-accent text-white" : "shadow-[inset_0_0_0_1.5px_var(--fm-border-strong)]")} aria-hidden>
                        {on && <Check size={14} strokeWidth={3} />}
                      </span>
                    </button>
                  );
                })}
              </div>
            </Step>

            <Step n={2} title="Dock video">
              <label
                onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
                onDragLeave={() => setDrag(false)}
                onDrop={(e) => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files[0]; if (f) setFile(f); }}
                className={cn("flex cursor-pointer flex-col items-center justify-center gap-2 rounded-fm border-2 border-dashed px-6 py-8 text-center transition-colors",
                  drag ? "border-fm-accent bg-fm-info-bg" : "border-fm-border-strong hover:border-fm-faint")}
              >
                <input type="file" accept="video/*" className="sr-only" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
                {file ? (
                  <span className="flex items-center gap-2 text-[15px] font-medium"><Film size={16} /> {file.name} <span className="text-fm-muted">{(file.size / 1e6).toFixed(1)} MB</span></span>
                ) : (
                  <>
                    <span className="flex h-11 w-11 items-center justify-center rounded-full bg-fm-raised text-fm-muted"><Upload size={18} /></span>
                    <span className="text-[15px] font-medium">Drop an MP4, or <span className="text-fm-accent-text">choose a file</span></span>
                    <span className="max-w-[44ch] text-[13px] text-fm-muted">
                      {IS_MOCK && selected ? `Demo build: replays the recorded ${selected.scenario_id}.mp4 if no file is attached.` : "Hashed with SHA-256 and uploaded once to the Files API."}
                    </span>
                  </>
                )}
              </label>
            </Step>

            <Step n={3} title="Storekeeper remark" hint="Optional">
              <div className="flex min-h-14 flex-wrap items-center gap-3 rounded-fm bg-fm-raised px-4 py-3">
                {voice.state === "idle" && (
                  <>
                    <Button type="button" size="md" variant="secondary" className="bg-fm-panel" onClick={() => void voice.start()}><Mic size={15} /> Record a remark</Button>
                    <span className="text-[13px] text-fm-muted">Context only. It never changes a count or a damage flag.</span>
                  </>
                )}
                {voice.state === "recording" && (
                  <>
                    <Button type="button" size="md" variant="danger" onClick={voice.stop}><Square size={13} fill="currentColor" /> Stop</Button>
                    <span className="flex items-center gap-2 text-[14px]" role="status" aria-live="off">
                      <span className="fm-live-dot inline-block h-2.5 w-2.5 rounded-full bg-fm-fraud-fill" aria-hidden />
                      Recording <span className="font-mono tabular-nums">{formatClock(voice.seconds)}</span> <span className="text-fm-faint">of {formatClock(voice.maxSeconds)}</span>
                    </span>
                  </>
                )}
                {voice.state === "recorded" && (
                  <>
                    <span className="flex items-center gap-2 text-[14px] font-medium"><Mic size={15} /> Remark recorded <span className="font-mono text-fm-muted">{formatClock(voice.seconds)}</span></span>
                    <span className="ml-auto flex gap-1">
                      <Button type="button" size="sm" variant="ghost" onClick={() => void voice.start()}><RotateCcw size={13} /> Re-record</Button>
                      <Button type="button" size="sm" variant="ghost" onClick={voice.remove}><Trash2 size={13} /> Remove</Button>
                    </span>
                  </>
                )}
                {voice.state === "denied" && (
                  <>
                    <span className="text-[14px] text-fm-muted">Microphone access was blocked. Allow it in the browser to record a remark.</span>
                    <Button type="button" size="sm" variant="secondary" className="ml-auto bg-fm-panel" onClick={() => void voice.start()}>Try again</Button>
                  </>
                )}
                {voice.state === "unsupported" && <span className="text-[14px] text-fm-muted">This browser cannot record audio. You can still start without a remark.</span>}
              </div>
            </Step>
            {create.isError && <p className="text-[14px] text-fm-fraud" role="alert">{create.error instanceof Error ? create.error.message : "Could not start the delivery."}</p>}
          </div>

          <div className="flex shrink-0 items-center justify-end gap-2 border-t border-fm-border px-8 py-5 max-sm:px-5">
            <Dialog.Close asChild><Button variant="ghost" size="lg">Cancel</Button></Dialog.Close>
            <Button variant="accent" size="lg" disabled={!poId || (needsFile && !file) || create.isPending} onClick={() => create.mutate()}>
              {create.isPending ? "Starting…" : "Start verification"}
            </Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
