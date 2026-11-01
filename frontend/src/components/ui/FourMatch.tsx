/** The signature visual: PO · GRN · Invoice · Vision. Three paper documents and one pair of
 *  eyes. When the fourth disagrees it takes an amber ring and the operator before it flips
 *  from "=" to "≠". */
import { Fragment, type ReactNode } from "react";
import { cn } from "../../lib/cn";
import { formatPct } from "../../lib/format";
import { SignalGlyph } from "./Glyph";
import { LiveCounter } from "./LiveCounter";

export type MatchKey = "po" | "grn" | "invoice" | "vision";
export interface MatchValues { po: number | null; grn: number | null; invoice: number | null; vision: number | null }

const LABEL: Record<MatchKey, string> = { po: "PO", grn: "GRN", invoice: "Invoice", vision: "Vision" };
const SOURCE: Record<MatchKey, string> = { po: "Purchase order", grn: "Goods receipt", invoice: "Vendor invoice", vision: "Dock video" };
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
            "w-[5px] rounded-full",
            k === "vision" ? "h-[16px]" : "h-[12px]",
            values[k] === null ? "bg-fm-hover" : mm[k] ? "bg-fm-hold-fill" : k === "vision" ? "bg-fm-verified-fill" : "bg-fm-faint",
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
  /** Vision is still counting: nothing is flagged yet and the figure ticks live. */
  live?: boolean;
  visionPending?: boolean;
  /** Shown under a mismatching vision tile. */
  variancePct?: number | null;
  size?: "md" | "lg";
  /** Tile fill: grey tiles inside a white card (default) or white tiles on the grey page. */
  surface?: "raised" | "panel";
  className?: string;
}

/** Four large tiles, one per source, with the operator between them. */
export function FourMatchStrip({ values, unit, sub, live, visionPending, variancePct, size = "md", surface = "raised", className }: StripProps) {
  const mm = live ? { po: false, grn: false, invoice: false, vision: false } : mismatches(values);
  const big = size === "lg";
  return (
    <div className={cn("grid items-stretch gap-y-3 max-md:grid-cols-2 max-md:gap-3 md:grid-cols-[1fr_auto_1fr_auto_1fr_auto_1fr]", className)}>
      {KEYS.map((k, i) => {
        const isVision = k === "vision";
        const bad = mm[k];
        const agrees = isVision && !bad && !live && values.vision !== null;
        const next = KEYS[i + 1];
        const nextBad = next ? mm[next] : false;
        return (
          <Fragment key={k}>
            <div
              className={cn(
                "relative flex min-w-0 flex-col rounded-fm transition-[background-color,box-shadow] duration-500 ease-[var(--fm-ease)]",
                big ? "min-h-[188px] p-6 max-md:min-h-[150px] max-md:p-5" : "min-h-[148px] p-5 max-md:min-h-[132px] max-md:p-4",
                surface === "panel" ? "bg-fm-panel" : "bg-fm-raised",
                bad && isVision && "bg-fm-hold-bg shadow-[inset_0_0_0_2px_var(--fm-hold-fill)]",
              )}
              data-match={k}
              data-mismatch={bad || undefined}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className={cn("text-[15px] font-semibold tracking-[-0.014em]", bad && "text-fm-hold")}>{LABEL[k]}</div>
                  <div className="truncate text-[12px] text-fm-muted max-sm:hidden">{SOURCE[k]}</div>
                </div>
                {isVision && live && (
                  <span className="flex shrink-0 items-center gap-1.5 text-[12px] font-semibold text-fm-accent-text">
                    <span className="fm-live-dot h-1.5 w-1.5 rounded-full bg-fm-accent" aria-hidden />Live
                  </span>
                )}
                {bad && isVision && <SignalGlyph signal="hold" size={15} className="mt-0.5 shrink-0 text-fm-hold" />}
                {agrees && <SignalGlyph signal="verified" size={14} className="mt-0.5 shrink-0 text-fm-verified" />}
              </div>
              <div className={cn("mt-auto flex items-baseline pt-4 leading-none", bad && "text-fm-hold")}>
                <span className={cn("fm-figure", big ? "text-[72px] max-md:text-[52px]" : "text-[52px] max-md:text-[44px]")}>
                  {values[k] === null ? (
                    <span className="text-fm-faint">{visionPending && isVision ? "·" : "—"}</span>
                  ) : isVision && live ? (
                    <LiveCounter value={values.vision ?? 0} label="Vision count" />
                  ) : (
                    values[k]
                  )}
                </span>
                {unit && values[k] !== null && <span className={cn("ml-1.5 text-[15px] font-medium text-fm-faint", bad && "text-fm-hold/70")}>{unit}</span>}
              </div>
              <div className="mt-2 line-clamp-2 min-h-[18px] text-[13px] leading-tight text-fm-muted">
                {isVision && bad && variancePct != null ? (
                  <span className="font-mono font-semibold text-fm-hold">{formatPct(variancePct)} vs PO</span>
                ) : (
                  sub?.[k]
                )}
              </div>
            </div>
            {next && (
              <div className="flex w-10 items-center justify-center max-md:hidden" aria-hidden>
                <span className={cn("text-[24px] font-light", nextBad ? "font-normal text-fm-hold" : "text-fm-faint")}>{nextBad ? "≠" : "="}</span>
              </div>
            )}
          </Fragment>
        );
      })}
    </div>
  );
}
