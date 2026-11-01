import { cn } from "../../lib/cn";

export interface SegOption<T extends string> { value: T; label: string; count?: number }

/** Segmented control (radio semantics): a white thumb on a grey track, optional counts. */
export function Segmented<T extends string>({ options, value, onChange, label }: {
  options: SegOption<T>[]; value: T; onChange: (v: T) => void; label: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="fm-scroll inline-flex max-w-full overflow-x-auto rounded-full bg-fm-hover/70 p-0.5 [scrollbar-width:none]">
      {options.map((o) => {
        const on = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={on}
            onClick={() => onChange(o.value)}
            className={cn(
              "inline-flex h-8 shrink-0 items-center gap-1.5 rounded-full px-3.5 text-[13px] font-medium transition-colors duration-200",
              on ? "fm-thumb text-fm-text" : "text-fm-muted hover:text-fm-text",
            )}
          >
            {o.label}
            {o.count !== undefined && <span className={cn("tabular-nums", on ? "text-fm-muted" : "text-fm-faint")}>{o.count}</span>}
          </button>
        );
      })}
    </div>
  );
}
