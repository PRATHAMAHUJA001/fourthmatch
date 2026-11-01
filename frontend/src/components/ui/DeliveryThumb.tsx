import { FileText } from "lucide-react";
import { cn } from "../../lib/cn";
import { frameFor } from "../../lib/media";
import type { CaseSummary } from "../../types/api";

/** Real dock frame for video deliveries; a quiet document tile for paper-only ones. */
export function DeliveryThumb({ c, className }: { c: CaseSummary; className?: string }) {
  const src = c.evidence_source === "video" ? frameFor(c.scenario_id) : undefined;
  return (
    <span className={cn("relative block shrink-0 overflow-hidden bg-fm-raised", className)}>
      {src ? (
        <img src={src} alt="" width={1280} height={720} decoding="async" className="h-full w-full object-cover" />
      ) : (
        <span className="flex h-full w-full flex-col items-center justify-center leading-none text-fm-muted" aria-hidden>
          <FileText size={14} strokeWidth={1.6} className="text-fm-faint" />
          <span className="mt-1 text-[10px] font-medium">Paper</span>
        </span>
      )}
    </span>
  );
}
