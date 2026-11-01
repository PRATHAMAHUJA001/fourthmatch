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
      className={cn("inline-flex h-5 shrink-0 items-center gap-1 whitespace-nowrap rounded-fm-sm border border-fm-hold-line bg-fm-hold-bg px-1.5 font-mono text-[10.5px] font-medium text-fm-hold", className)}
      data-testid="remark-not-supported"
    >
      <SignalGlyph signal="fraud" size={10} /> Remark not supported by video
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
  supported: { icon: <Check size={12} />, label: "Supported" },
  not_supported: { icon: <X size={12} />, label: "Not supported" },
  unverifiable: { icon: <CircleHelp size={12} />, label: "Cannot verify" },
};

/** Storekeeper voice remark: shown as context, never as evidence. */
export function RemarkPanel({ remark }: { remark: RemarkRead }) {
  const status = remark.check?.status;
  return (
    <Panel
      index="06"
      title="Storekeeper remark"
      subtitle="context, not evidence"
      actions={status === "not_supported" ? <RemarkNotSupportedChip /> : undefined}
    >
      <p className="fm-label mb-1">Storekeeper remark — context, not evidence</p>
      <blockquote className="border-l-2 border-fm-border-strong pl-3 text-[13px] italic leading-relaxed text-fm-text">“{remark.transcript}”</blockquote>
      {remark.check ? (
        <div className="mt-3 flex flex-col gap-2">
          <p className="flex items-center gap-1.5 text-[12px] text-fm-muted">
            {status === "no_claim" ? <Minus size={12} /> : null}
            {status ? STATUS_TEXT[status] : null}
          </p>
          {remark.check.items.length > 0 && (
            <ul className="flex flex-col gap-1">
              {remark.check.items.map((item, i) => (
                <li key={i} className="flex items-center gap-2 text-[12px]">
                  <span className={cn("inline-flex h-5 shrink-0 items-center gap-1 rounded-fm-sm border px-1.5 font-mono text-[10.5px]",
                    item.verdict === "not_supported" ? "border-fm-hold-line bg-fm-hold-bg text-fm-hold" : "border-fm-border bg-fm-raised text-fm-muted")}>
                    {VERDICT[item.verdict].icon}{VERDICT[item.verdict].label}
                  </span>
                  <span className="min-w-0 truncate">{item.claim.text}</span>
                  {item.observed !== null && <span className="ml-auto shrink-0 font-mono text-[11px] text-fm-faint">video: {item.observed}</span>}
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : (
        <p className="mt-3 text-[12px] text-fm-muted">Not checked yet.</p>
      )}
      <p className="mt-3 text-[11px] text-fm-faint">Transcribed by muse-voice-transcribe-1.0. It never changes a count, a damage flag or the verdict.</p>
    </Panel>
  );
}
