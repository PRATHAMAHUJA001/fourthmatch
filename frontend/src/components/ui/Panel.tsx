import type { ReactNode } from "react";
import { cn } from "../../lib/cn";

interface PanelProps {
  title?: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
  padded?: boolean;
  className?: string;
  bodyClassName?: string;
}

export function Panel({ title, subtitle, actions, children, padded = true, className, bodyClassName }: PanelProps) {
  return (
    <section className={cn("rounded-fm border border-fm-border bg-fm-panel", className)}>
      {(title || actions) && (
        <header className="flex min-h-9 items-center justify-between gap-3 border-b border-fm-border px-3 py-2">
          <div className="min-w-0">
            {title && <h2 className="truncate text-[12px] font-semibold uppercase tracking-[0.05em]">{title}</h2>}
            {subtitle && <p className="truncate text-[11px] text-fm-muted">{subtitle}</p>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={cn(padded && "p-3", bodyClassName)}>{children}</div>
    </section>
  );
}
