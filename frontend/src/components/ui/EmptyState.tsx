import { Inbox } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "../../lib/cn";

export function EmptyState({ title, description, action, className }: {
  title: string; description?: string; action?: ReactNode; className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center gap-1.5 px-4 py-10 text-center", className)}>
      <Inbox size={20} className="text-fm-faint" aria-hidden />
      <p className="text-[13px] font-semibold">{title}</p>
      {description && <p className="max-w-sm text-[12px] text-fm-muted">{description}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("fm-skeleton rounded-fm-sm", className)} aria-hidden />;
}

export function SkeletonRows({ rows = 4 }: { rows?: number }) {
  return (
    <div className="flex flex-col gap-2" role="status" aria-label="Loading">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-8 w-full" />
      ))}
    </div>
  );
}
