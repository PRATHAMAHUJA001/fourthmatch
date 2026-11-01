import * as Dialog from "@radix-ui/react-dialog";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Film, Mic, RotateCcw, Square, Trash2, Upload, X } from "lucide-react";
import { useState } from "react";
import { api } from "../../lib/api";
import { cn } from "../../lib/cn";
import { IS_MOCK } from "../../lib/demo";
import { formatClock, useVoiceRecorder } from "../../lib/useVoiceRecorder";
import { formatINR } from "../../lib/format";
import { Button } from "../ui/Button";
import { Tag } from "../ui/Tag";

/** Pick a PO, drop the dock video, start the pipeline. */
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
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/55" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[min(560px,calc(100vw-32px))] -translate-x-1/2 -translate-y-1/2 rounded-fm border border-fm-border-strong bg-fm-panel">
          <div className="flex items-center justify-between border-b border-fm-border px-4 py-3">
            <Dialog.Title className="text-[14px] font-semibold">New delivery</Dialog.Title>
            <Dialog.Close className="rounded-fm-sm p-1 text-fm-muted hover:bg-fm-raised hover:text-fm-text" aria-label="Close"><X size={15} /></Dialog.Close>
          </div>
          <Dialog.Description className="px-4 pt-3 text-[12.5px] text-fm-muted">
            Pick the purchase order this truck is delivering against, then attach the dock video. Muse Spark picks what to track, SAM 3.1 tracks it, the agent decides.
          </Dialog.Description>
          <div className="flex flex-col gap-4 p-4">
            <fieldset>
              <legend className="fm-label mb-1.5">1 · Purchase order</legend>
              <div className="flex flex-col gap-1" role="radiogroup">
                {pos.isLoading && <div className="fm-skeleton h-24" />}
                {videoPos.map((p) => (
                  <button
                    key={p.id}
                    type="button"
                    role="radio"
                    aria-checked={poId === p.id}
                    onClick={() => setPoId(p.id)}
                    className={cn("flex h-10 items-center gap-3 rounded-fm-sm border px-3 text-left transition-colors",
                      poId === p.id ? "border-fm-hold bg-fm-hold-bg" : "border-fm-border hover:bg-fm-raised")}
                  >
                    <span className={cn("h-3 w-3 shrink-0 rounded-full border", poId === p.id ? "border-[4px] border-fm-hold" : "border-fm-border-strong")} />
                    <span className="font-mono text-[12.5px]">{p.po_number}</span>
                    <span className="truncate text-[12px] text-fm-muted">{p.vendor_name}</span>
                    <span className="ml-auto flex items-center gap-2">
                      <span className="font-mono text-[11px] text-fm-faint">{formatINR(p.total_paise)}</span>
                      <Tag>{p.scenario_id}</Tag>
                    </span>
                  </button>
                ))}
              </div>
            </fieldset>
            <div>
              <div className="fm-label mb-1.5">2 · Dock video</div>
              <label
                onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
                onDragLeave={() => setDrag(false)}
                onDrop={(e) => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files[0]; if (f) setFile(f); }}
                className={cn("fm-dotgrid flex cursor-pointer flex-col items-center justify-center gap-1.5 rounded-fm border border-dashed px-4 py-6 text-center transition-colors",
                  drag ? "border-fm-hold bg-fm-hold-bg" : "border-fm-border-strong hover:border-fm-muted")}
              >
                <input type="file" accept="video/*" className="sr-only" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
                {file ? (
                  <span className="flex items-center gap-2 font-mono text-[12px]"><Film size={14} /> {file.name} · {(file.size / 1e6).toFixed(1)} MB</span>
                ) : (
                  <>
                    <Upload size={16} className="text-fm-muted" />
                    <span className="text-[12.5px]">Drop an MP4 or click to browse</span>
                    <span className="text-[11px] text-fm-faint">
                      {IS_MOCK && selected ? `Demo: replays the recorded ${selected.scenario_id}.mp4 if no file is attached` : "Hashed with SHA-256 and uploaded once to the Files API"}
                    </span>
                  </>
                )}
              </label>
            </div>
            <div>
              <div className="fm-label mb-1.5">3 · Storekeeper remark <span className="normal-case text-fm-faint">(optional)</span></div>
              <div className="flex min-h-10 flex-wrap items-center gap-2 rounded-fm border border-fm-border px-3 py-2">
                {voice.state === "idle" && (
                  <Button type="button" size="sm" variant="secondary" onClick={() => void voice.start()}><Mic size={13} /> Record remark</Button>
                )}
                {voice.state === "recording" && (
                  <>
                    <Button type="button" size="sm" variant="danger" onClick={voice.stop}><Square size={12} /> Stop</Button>
                    <span className="flex items-center gap-2 font-mono text-[12px]" role="status" aria-live="off">
                      <span className="fm-live-dot inline-block h-2 w-2 rounded-full bg-fm-fraud" aria-hidden />
                      Recording {formatClock(voice.seconds)} / {formatClock(voice.maxSeconds)}
                    </span>
                  </>
                )}
                {voice.state === "recorded" && (
                  <>
                    <span className="flex items-center gap-2 font-mono text-[12px]"><Mic size={13} /> Remark recorded · {formatClock(voice.seconds)}</span>
                    <span className="ml-auto flex gap-1">
                      <Button type="button" size="xs" variant="ghost" onClick={() => void voice.start()}><RotateCcw size={12} /> Re-record</Button>
                      <Button type="button" size="xs" variant="ghost" onClick={voice.remove}><Trash2 size={12} /> Remove</Button>
                    </span>
                  </>
                )}
                {voice.state === "denied" && (
                  <>
                    <span className="text-[12px] text-fm-muted">Microphone access was blocked. Allow it in the browser to record a remark.</span>
                    <Button type="button" size="xs" variant="ghost" className="ml-auto" onClick={() => void voice.start()}>Try again</Button>
                  </>
                )}
                {voice.state === "unsupported" && <span className="text-[12px] text-fm-muted">This browser cannot record audio. You can still start without a remark.</span>}
                {(voice.state === "idle" || voice.state === "denied") && (
                  <span className="text-[11px] text-fm-faint">Transcribed as context only. It never changes a count or a damage flag.</span>
                )}
              </div>
            </div>
            {create.isError && <p className="text-[12px] text-fm-fraud" role="alert">{create.error instanceof Error ? create.error.message : "Could not start the delivery."}</p>}
          </div>
          <div className="flex items-center justify-between gap-2 border-t border-fm-border px-4 py-3">
            <span className="font-mono text-[10.5px] text-fm-faint">POST /api/deliveries</span>
            <div className="flex gap-2">
              <Dialog.Close asChild><Button variant="ghost" size="sm">Cancel</Button></Dialog.Close>
              <Button variant="accent" size="sm" disabled={!poId || (needsFile && !file) || create.isPending} onClick={() => create.mutate()}>
                {create.isPending ? "Starting…" : "Start verification"}
              </Button>
            </div>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
