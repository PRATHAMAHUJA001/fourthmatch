import { Check, X } from "lucide-react";
import { cn } from "../../lib/cn";
import type { JobStatus } from "../../types/api";

const ORDER: JobStatus[] = ["queued", "uploading", "understanding", "tracking", "damage_check", "done"];
const LABELS: Record<JobStatus, string> = {
  queued: "Queued", uploading: "Upload", understanding: "Understand",
  tracking: "SAM tracking", damage_check: "Damage check", done: "Done", failed: "Failed",
};

export function Stepper({ current, failed }: { current: JobStatus; failed?: boolean }) {
  const isFailed = failed || current === "failed";
  const currentIdx = isFailed ? ORDER.length - 2 : Math.max(0, ORDER.indexOf(current));

  return (
    <ol className="flex items-center gap-0" aria-label="Pipeline progress">
      {ORDER.map((step, i) => {
        const done = !isFailed && i < currentIdx;
        const active = !isFailed && i === currentIdx;
        const failedStep = isFailed && i === currentIdx;
        return (
          <li key={step} className="flex items-center">
            <span className="flex items-center gap-1.5">
              <span
                className={cn(
                  "flex h-5 w-5 items-center justify-center rounded-full border font-mono text-[10px]",
                  done && "border-fm-verified bg-fm-verified-bg text-fm-verified",
                  active && "border-fm-hold bg-fm-hold-bg text-fm-hold",
                  failedStep && "border-fm-fraud bg-fm-fraud-bg text-fm-fraud",
                  !done && !active && !failedStep && "border-fm-border-strong text-fm-faint",
                )}
                aria-current={active ? "step" : undefined}
              >
                {done ? <Check size={11} strokeWidth={3} /> : failedStep ? <X size={11} strokeWidth={3} /> : i + 1}
              </span>
              <span className={cn("hidden text-[11px] sm:inline", active ? "font-semibold" : "text-fm-muted", failedStep && "font-semibold text-fm-fraud")}>
                {LABELS[step]}
              </span>
            </span>
            {i < ORDER.length - 1 && (
              <span className={cn("mx-2 h-px w-6 sm:w-10", done ? "bg-fm-verified" : "bg-fm-border-strong")} aria-hidden />
            )}
          </li>
        );
      })}
    </ol>
  );
}
