import { cn } from "../../lib/cn";
import { VERDICT_LABEL, type EvalRead } from "../../types/api";

/** Rows = ground truth, columns = agent verdict. Diagonal = correct. */
export function ConfusionMatrix({ data }: { data: EvalRead["confusion"] }) {
  const { labels, matrix } = data;
  const n = labels.length;
  return (
    <div className="flex items-stretch gap-2">
      <div className="fm-label flex items-center justify-center [writing-mode:vertical-rl] rotate-180">Ground truth</div>
      <div className="min-w-0 flex-1">
        <div className="grid gap-1" style={{ gridTemplateColumns: `minmax(72px,96px) repeat(${n}, minmax(0, 1fr))` }} role="table" aria-label="Confusion matrix">
          <div />
          {labels.map((l) => (
            <div key={l} className="fm-label truncate pb-1 text-center !text-[10px]" role="columnheader">{VERDICT_LABEL[l]}</div>
          ))}
          {labels.map((rl, r) => (
            <div key={rl} className="contents" role="row">
              <div className="flex items-center justify-end pr-2 text-right font-cond text-[11px] font-semibold uppercase tracking-[0.06em] text-fm-muted" role="rowheader">{VERDICT_LABEL[rl]}</div>
              {labels.map((cl, c) => {
                const v = matrix[r][c];
                const diag = r === c;
                return (
                  <div
                    key={cl}
                    role="cell"
                    aria-label={`Truth ${VERDICT_LABEL[rl]}, predicted ${VERDICT_LABEL[cl]}: ${v}`}
                    className={cn(
                      "flex aspect-square max-h-[64px] items-center justify-center rounded-fm-sm border font-mono text-[18px] font-medium tabular-nums",
                      v === 0 && "border-fm-border text-fm-faint opacity-60",
                      v > 0 && diag && "border-fm-verified-line bg-fm-verified-bg text-fm-verified",
                      v > 0 && !diag && "border-fm-fraud-line bg-fm-fraud-bg text-fm-fraud",
                    )}
                  >
                    {v}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
        <div className="fm-label mt-2 text-center">Agent verdict</div>
      </div>
    </div>
  );
}
