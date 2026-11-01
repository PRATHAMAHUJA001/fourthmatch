import type { ReactNode } from "react";
import { cn } from "../../lib/cn";
import { BrandMark } from "../shell/BrandMark";

export function EmptyState({ title, description, action, className }: {
  title: string; description?: string; action?: ReactNode; className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center gap-2 px-6 py-14 text-center", className)}>
      <BrandMark size={26} muted />
      <p className="mt-2 text-[17px] font-semibold tracking-[-0.016em]">{title}</p>
      {description && <p className="max-w-sm text-[14px] text-fm-muted">{description}</p>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("fm-skeleton", className)} aria-hidden />;
}

export function SkeletonRows({ rows = 4, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn("flex flex-col gap-1.5", className)} role="status" aria-label="Loading">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-9 w-full" />
      ))}
    </div>
  );
}

export function ErrorState({ message, action }: { message: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 px-4 py-10 text-center" role="alert">
      <p className="text-[15px] font-semibold text-fm-fraud">Request failed</p>
      <p className="max-w-md text-[14px] text-fm-muted">{message}</p>
      {action}
    </div>
  );
}
