import { cn } from "../../lib/cn";

export interface SegOption<T extends string> { value: T; label: string; count?: number }

/** Flat segmented control (radio semantics) with optional counts. */
export function Segmented<T extends string>({ options, value, onChange, label }: {
  options: SegOption<T>[]; value: T; onChange: (v: T) => void; label: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex max-w-full overflow-x-auto rounded-fm-sm border border-fm-border-strong bg-fm-sunken p-0.5 fm-scroll">
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
              "inline-flex h-6 shrink-0 items-center gap-1.5 rounded-[2px] px-2 text-[12px] font-medium transition-colors duration-[var(--fm-motion)]",
              on ? "bg-fm-raised text-fm-text ring-1 ring-inset ring-fm-border-strong" : "text-fm-muted hover:text-fm-text",
            )}
          >
            {o.label}
            {o.count !== undefined && (
              <span className={cn("font-mono text-[10.5px] tabular-nums", on ? "text-fm-hold" : "text-fm-faint")}>{o.count}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}
