import type { ReactNode } from "react";
import { cn } from "../../lib/cn";

interface PanelProps {
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  padded?: boolean;
  className?: string;
  bodyClassName?: string;
  as?: "section" | "div" | "aside";
}

/** Card. Elevation by fill only: a white surface on the grey page, no border, no shadow.
 *  The title sits inside the card's padding; no divider line under it. */
export function Panel({ title, subtitle, actions, children, padded = true, className, bodyClassName, as: As = "section" }: PanelProps) {
  return (
    <As className={cn("flex min-w-0 flex-col rounded-fm bg-fm-panel", className)}>
      {(title || actions) && (
        <header className="flex shrink-0 flex-wrap items-baseline justify-between gap-x-4 gap-y-1 px-6 pb-1 pt-5 max-sm:px-5">
          <div className="min-w-0">
            {title && <h2 className="text-[19px] font-semibold leading-tight tracking-[-0.022em] text-fm-text">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-[13px] text-fm-muted">{subtitle}</p>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={cn("min-h-0 flex-1", padded && "px-6 pb-6 pt-4 max-sm:px-5 max-sm:pb-5", padded && !title && !actions && "pt-6 max-sm:pt-5", bodyClassName)}>{children}</div>
    </As>
  );
}

/** Page header: a large title with one calm line of context underneath; actions on the right. */
export function PageHeader({ eyebrow, title, meta, actions, className }: {
  eyebrow?: ReactNode; title: ReactNode; meta?: ReactNode; actions?: ReactNode; className?: string;
}) {
  return (
    <div className={cn("mb-10 flex flex-wrap items-end justify-between gap-x-6 gap-y-5 pt-6 max-sm:mb-8 max-sm:pt-2", className)}>
      <div className="min-w-0 max-w-3xl">
        {eyebrow && <div className="mb-2 text-[15px] font-semibold tracking-[-0.012em] text-fm-muted">{eyebrow}</div>}
        <h1 className="text-[40px] font-bold leading-[1.05] tracking-[-0.034em] sm:text-[52px]">{title}</h1>
        {meta && <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1 text-[17px] leading-snug tracking-[-0.012em] text-fm-muted">{meta}</div>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
