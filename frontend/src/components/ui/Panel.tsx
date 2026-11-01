import type { ReactNode } from "react";
import { cn } from "../../lib/cn";

interface PanelProps {
  title?: ReactNode;
  /** Optional short index shown before the title, e.g. "01". */
  index?: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  padded?: boolean;
  /** Deprecated: viewfinder ticks do not suit rounded cards; kept for API compatibility. */
  ticks?: boolean;
  className?: string;
  bodyClassName?: string;
  as?: "section" | "div" | "aside";
}

/** Card. Elevation by fill only: a white surface on the grey page (no border, no shadow).
 *  The header is a quiet title row; a hairline separates it from the body. */
export function Panel({ title, index, subtitle, actions, children, padded = true, ticks, className, bodyClassName, as: As = "section" }: PanelProps) {
  return (
    <As className={cn("flex min-w-0 flex-col rounded-fm bg-fm-panel", className)} data-ticks={ticks || undefined}>
      {(title || actions) && (
        <header className="flex min-h-12 shrink-0 items-center justify-between gap-3 border-b border-fm-border px-5 py-2.5">
          <div className="flex min-w-0 items-baseline gap-2.5">
            {index && <span className="font-mono text-[11px] text-fm-faint">{index}</span>}
            {title && <h2 className="truncate text-[15px] font-semibold tracking-[-0.016em] text-fm-text">{title}</h2>}
            {subtitle && <span className="truncate text-[12.5px] text-fm-muted">{subtitle}</span>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-1.5">{actions}</div>}
        </header>
      )}
      <div className={cn("min-h-0 flex-1", padded && "p-5", bodyClassName)}>{children}</div>
    </As>
  );
}

/** Page header: eyebrow + large title + meta row + actions. */
export function PageHeader({ eyebrow, title, meta, actions, className }: {
  eyebrow?: ReactNode; title: ReactNode; meta?: ReactNode; actions?: ReactNode; className?: string;
}) {
  return (
    <div className={cn("mb-8 flex flex-wrap items-end justify-between gap-4 pt-2", className)}>
      <div className="min-w-0">
        {eyebrow && <div className="mb-1.5 text-[14px] font-semibold tracking-[-0.01em] text-fm-muted">{eyebrow}</div>}
        <h1 className="text-[34px] font-bold leading-[1.08] tracking-[-0.03em] sm:text-[40px]">{title}</h1>
        {meta && <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[14px] text-fm-muted">{meta}</div>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
