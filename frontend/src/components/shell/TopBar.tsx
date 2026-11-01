import { Search } from "lucide-react";
import { forwardRef } from "react";

export const TopBar = forwardRef<HTMLInputElement, { onSearchFocus?: () => void }>(function TopBar(_props, searchRef) {
  return (
    <header className="flex h-12 shrink-0 items-center gap-3 border-b border-fm-border bg-fm-panel px-3">
      <div className="flex items-center gap-2.5">
        <span className="flex h-6 w-6 items-center justify-center rounded-fm-sm bg-fm-text font-mono text-[11px] font-bold text-fm-bg" aria-hidden>
          4M
        </span>
        <span className="text-[14px] font-semibold tracking-tight">FourthMatch</span>
        <span className="hidden rounded-fm-sm border border-fm-hold/40 bg-fm-hold-bg px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-[0.05em] text-fm-hold sm:inline">
          Synthetic data
        </span>
      </div>

      <div className="relative mx-auto w-full max-w-md">
        <Search size={14} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-fm-faint" aria-hidden />
        <input
          ref={searchRef}
          type="search"
          placeholder="Search PO, vendor, invoice…  ( / )"
          aria-label="Global search"
          className="h-8 w-full rounded-fm-sm border border-fm-border bg-fm-bg pl-8 pr-12 font-mono text-[12px] placeholder:font-sans placeholder:text-fm-faint"
        />
        <kbd className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 rounded border border-fm-border-strong bg-fm-raised px-1 font-mono text-[10px] text-fm-muted">/</kbd>
      </div>

      <div className="hidden items-center gap-2 text-[11px] text-fm-muted md:flex">
        <span className="flex items-center gap-1.5">
          <span className="fm-live-dot h-1.5 w-1.5 rounded-full bg-fm-verified" aria-hidden />
          <span className="font-mono">DOCK-01 · LIVE</span>
        </span>
      </div>
    </header>
  );
});
