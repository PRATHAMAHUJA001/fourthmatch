import type { ReactNode } from "react";
import { cn } from "../../lib/cn";

interface PanelProps {
  title?: ReactNode;
  /** Short mono index shown before the title, e.g. "01". Gives panels an instrument-sheet rhythm. */
  index?: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  padded?: boolean;
  ticks?: boolean;
  className?: string;
  bodyClassName?: string;
  as?: "section" | "div" | "aside";
}

/** Hairline panel. Header is a thin label strip, not a card title. */
export function Panel({ title, index, subtitle, actions, children, padded = true, ticks, className, bodyClassName, as: As = "section" }: PanelProps) {
  return (
    <As className={cn("flex min-w-0 flex-col rounded-fm border border-fm-border bg-fm-panel", ticks && "fm-ticks", className)}>
      {(title || actions) && (
        <header className="flex min-h-9 shrink-0 items-center justify-between gap-3 border-b border-fm-border px-3 py-1.5">
          <div className="flex min-w-0 items-baseline gap-2">
            {index && <span className="font-mono text-[10px] text-fm-faint">{index}</span>}
            {title && <h2 className="fm-label truncate !text-fm-text">{title}</h2>}
            {subtitle && <span className="truncate text-[11.5px] text-fm-muted">{subtitle}</span>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-1.5">{actions}</div>}
        </header>
      )}
      <div className={cn("min-h-0 flex-1", padded && "p-3", bodyClassName)}>{children}</div>
    </As>
  );
}

/** Page header: eyebrow + title + meta row + actions. */
export function PageHeader({ eyebrow, title, meta, actions, className }: {
  eyebrow?: ReactNode; title: ReactNode; meta?: ReactNode; actions?: ReactNode; className?: string;
}) {
  return (
    <div className={cn("mb-4 flex flex-wrap items-end justify-between gap-3", className)}>
      <div className="min-w-0">
        {eyebrow && <div className="fm-label mb-1">{eyebrow}</div>}
        <h1 className="text-[22px] font-semibold leading-tight tracking-[-0.015em]">{title}</h1>
        {meta && <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-fm-muted">{meta}</div>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
