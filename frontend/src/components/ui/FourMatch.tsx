/** The signature visual: PO · GRN · Invoice · Vision. Three paper documents and one
 *  pair of eyes. When the fourth disagrees, it lights up and the operator between
 *  them flips from "=" to "≠". */
import { Fragment, type ReactNode } from "react";
import { cn } from "../../lib/cn";
import { formatPct } from "../../lib/format";
import { LiveCounter } from "./LiveCounter";

export type MatchKey = "po" | "grn" | "invoice" | "vision";
export interface MatchValues { po: number | null; grn: number | null; invoice: number | null; vision: number | null }

const LABEL: Record<MatchKey, string> = { po: "PO", grn: "GRN", invoice: "Invoice", vision: "Vision" };
const KEYS: MatchKey[] = ["po", "grn", "invoice", "vision"];

/** Which cells disagree with the purchase order. Pure; unit-tested. */
export function mismatches(v: MatchValues): Record<MatchKey, boolean> {
  const ref = v.po;
  const off = (x: number | null) => ref !== null && x !== null && x !== ref;
  return { po: false, grn: off(v.grn), invoice: off(v.invoice), vision: off(v.vision) };
}

/** Compact four-bar indicator for table rows. */
export function FourMatchMini({ values, className }: { values: MatchValues; className?: string }) {
  const mm = mismatches(values);
  const label = KEYS.map((k) => `${LABEL[k]} ${values[k] ?? "—"}${mm[k] ? " (mismatch)" : ""}`).join(", ");
  return (
    <span className={cn("inline-flex items-end gap-[3px]", className)} role="img" aria-label={label} title={label}>
      {KEYS.map((k) => (
        <span
          key={k}
          className={cn(
            "w-[5px] rounded-[1px]",
            k === "vision" ? "h-[16px]" : "h-[12px]",
            values[k] === null ? "bg-fm-border" : mm[k] ? "bg-fm-hold" : k === "vision" ? "bg-fm-verified" : "bg-fm-muted",
          )}
        />
      ))}
    </span>
  );
}

interface StripProps {
  values: MatchValues;
  unit?: string;
  sub?: Partial<Record<MatchKey, ReactNode>>;
  /** Shown under a mismatching vision cell, e.g. variance. */
  live?: boolean;
  visionPending?: boolean;
  variancePct?: number | null;
  size?: "md" | "lg";
  className?: string;
}

/** Full strip for the case page and the landing hero. */
export function FourMatchStrip({ values, unit, sub, live, visionPending, variancePct, size = "md", className }: StripProps) {
  // While vision is still counting, nothing is flagged yet.
  const mm = live ? { po: false, grn: false, invoice: false, vision: false } : mismatches(values);
  const big = size === "lg";
  return (
    <div className={cn("grid items-stretch", big ? "grid-cols-[1fr_auto_1fr_auto_1fr_auto_1.15fr]" : "grid-cols-[1fr_auto_1fr_auto_1fr_auto_1.15fr]", className)}>
      {KEYS.map((k, i) => {
        const isVision = k === "vision";
        const bad = mm[k];
        const next = KEYS[i + 1];
        const nextBad = next ? mm[next] : false;
        return (
          <Fragment key={k}>
            <div
              className={cn(
                "relative flex min-w-0 flex-col justify-between rounded-fm border bg-fm-raised",
                big ? "gap-3 px-4 py-3.5" : "gap-2 px-3 py-2.5",
                isVision ? "border-fm-border-strong" : "border-fm-border",
                bad && isVision && "fm-glow-hold border-fm-hold bg-fm-hold-bg",
                bad && !isVision && "border-fm-hold-line",
                isVision && !bad && values.vision !== null && "border-fm-verified-line bg-fm-verified-bg",
              )}
            >
              <div className="flex items-center justify-between gap-1">
                <span className={cn("fm-label", isVision && "!text-fm-text", bad && "!text-fm-hold")}>
                  {isVision && <span className="mr-1 text-fm-hold">◉</span>}{LABEL[k]}
                </span>
                {isVision && live && <span className="font-mono text-[9.5px] font-semibold tracking-[0.08em] text-fm-hold">LIVE</span>}
              </div>
              <div className={cn("font-mono font-medium leading-none tracking-[-0.04em] tabular-nums", big ? "text-[44px]" : "text-[30px]", bad && "text-fm-hold", isVision && !bad && values.vision !== null && "text-fm-verified")}>
                {values[k] === null ? (
                  <span className="text-fm-faint">{visionPending && isVision ? "··" : "—"}</span>
                ) : isVision && live ? (
                  <LiveCounter value={values.vision ?? 0} digits={String(values.po ?? 10).length} />
                ) : (
                  values[k]
                )}
                {unit && values[k] !== null && <span className={cn("ml-1 font-sans font-normal tracking-normal text-fm-faint", big ? "text-[14px]" : "text-[11px]")}>{unit}</span>}
              </div>
              <div className="line-clamp-2 min-h-[16px] break-words text-[11px] leading-tight text-fm-muted">
                {isVision && bad && variancePct != null ? (
                  <span className="font-mono font-semibold text-fm-hold">{formatPct(variancePct)} vs PO</span>
                ) : (
                  sub?.[k]
                )}
              </div>
            </div>
            {next && (
              <div className="flex w-6 items-center justify-center" aria-hidden>
                <span className={cn("font-mono text-[16px] font-semibold", nextBad ? "text-fm-hold" : "text-fm-faint")}>{nextBad ? "≠" : "="}</span>
              </div>
            )}
          </Fragment>
        );
      })}
    </div>
  );
}
