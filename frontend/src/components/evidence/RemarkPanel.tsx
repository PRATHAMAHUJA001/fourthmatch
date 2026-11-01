import { Check, CircleHelp, Minus, X } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "../../lib/cn";
import type { ClaimVerdict, RemarkRead, RemarkStatus } from "../../types/api";
import { Panel } from "../ui/Panel";
import { SignalGlyph } from "../ui/Glyph";

/** Chip for a remark that the video contradicts. Icon + text, never colour alone. */
export function RemarkNotSupportedChip({ className }: { className?: string }) {
  return (
    <span
      className={cn("inline-flex h-7 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full bg-fm-hold-bg px-3 text-[13px] font-semibold text-fm-hold", className)}
      data-testid="remark-not-supported"
    >
      <SignalGlyph signal="fraud" size={12} /> Remark not supported by video
    </span>
  );
}

const STATUS_TEXT: Record<RemarkStatus, string> = {
  supported: "Consistent with the video",
  not_supported: "Remark not supported by video",
  no_claim: "Nothing in the remark can be checked against the video",
  unverifiable: "The video cannot confirm or refute the remark",
};

const VERDICT: Record<ClaimVerdict, { icon: ReactNode; label: string }> = {
  supported: { icon: <Check size={13} />, label: "Supported" },
  not_supported: { icon: <X size={13} />, label: "Not supported" },
  unverifiable: { icon: <CircleHelp size={13} />, label: "Cannot verify" },
};

/** Storekeeper voice remark: shown as context, never as evidence. */
export function RemarkPanel({ remark }: { remark: RemarkRead }) {
  const status = remark.check?.status;
  return (
    <Panel title="Storekeeper remark" actions={status === "not_supported" ? <RemarkNotSupportedChip /> : undefined}>
      <p className="fm-label mb-3">Storekeeper remark — context, not evidence</p>
      <blockquote className="text-[19px] font-medium leading-[1.4] tracking-[-0.016em] text-fm-text">“{remark.transcript}”</blockquote>
      {remark.check ? (
        <div className="mt-4 flex flex-col gap-2">
          <p className="flex items-center gap-1.5 text-[13px] text-fm-muted">
            {status === "no_claim" ? <Minus size={13} /> : null}
            {status ? STATUS_TEXT[status] : null}
          </p>
          {remark.check.items.length > 0 && (
            <ul className="flex flex-col divide-y divide-fm-border rounded-[12px] bg-fm-raised px-3.5">
              {remark.check.items.map((item, i) => (
                <li key={i} className="flex min-h-11 items-center gap-3 text-[13px]">
                  <span className={cn("inline-flex shrink-0 items-center gap-1 text-[12px] font-semibold", item.verdict === "not_supported" ? "text-fm-hold" : "text-fm-muted")}>
                    {VERDICT[item.verdict].icon}{VERDICT[item.verdict].label}
                  </span>
                  <span className="min-w-0 truncate">{item.claim.text}</span>
                  {item.observed !== null && <span className="ml-auto shrink-0 text-[12px] text-fm-muted">Video: <span className="font-mono text-fm-text">{item.observed}</span></span>}
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : (
        <p className="mt-4 text-[13px] text-fm-muted">Not checked yet.</p>
      )}
      <p className="mt-4 text-[12px] text-fm-faint">Transcribed by muse-voice-transcribe-1.0. It never changes a count, a damage flag or the verdict.</p>
    </Panel>
  );
}
