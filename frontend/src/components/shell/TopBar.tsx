import { Search } from "lucide-react";
import { Link, useLocation } from "react-router-dom";
import { IS_MOCK } from "../../lib/demo";
import { Kbd } from "../ui/Tag";
import { Wordmark } from "./BrandMark";
import { NAV } from "./nav";

function crumbs(pathname: string): string[] {
  const parts = pathname.split("/").filter(Boolean);
  const nav = NAV.find((n) => n.to === `/${parts[0]}`);
  const out = [nav?.label ?? (parts[0] === "styleguide" ? "Design system" : parts[0] ?? "")];
  if (parts[1]) out.push(`PO ${parts[1].padStart(3, "0")}`);
  return out.filter(Boolean);
}

export function TopBar({ onOpenPalette }: { onOpenPalette: () => void }) {
  const { pathname } = useLocation();
  const c = crumbs(pathname);
  return (
    <header className="flex h-11 shrink-0 items-center gap-3 border-b border-fm-border bg-fm-panel pl-3 pr-2">
      <Link to="/" className="flex items-center rounded-fm-sm pr-1" aria-label="FourthMatch home">
        <Wordmark />
      </Link>
      <span className="h-4 w-px bg-fm-border-strong max-sm:hidden" aria-hidden />
      <nav aria-label="Breadcrumb" className="flex min-w-0 items-center gap-1.5 text-[12.5px] max-sm:hidden">
        {c.map((x, i) => (
          <span key={i} className="flex items-center gap-1.5 truncate">
            {i > 0 && <span className="text-fm-faint">/</span>}
            <span className={i === c.length - 1 ? "font-medium" : "text-fm-muted"}>{x}</span>
          </span>
        ))}
      </nav>
      <span
        className="ml-1 inline-flex h-5 shrink-0 items-center gap-1.5 rounded-fm-sm border border-dashed border-fm-hold-line px-1.5 font-cond text-[10px] font-semibold uppercase tracking-[0.08em] text-fm-hold"
        title="Every vendor, PO, invoice and video in this product is synthetic."
      >
        Synthetic data
      </span>

      <button
        type="button"
        onClick={onOpenPalette}
        aria-label="Global search"
        className="ml-auto flex h-7 w-auto min-w-0 items-center sm:w-full sm:max-w-[340px] gap-2 rounded-fm-sm border border-fm-border bg-fm-bg px-2 text-left text-[12px] text-fm-faint transition-colors hover:border-fm-border-strong hover:text-fm-muted"
      >
        <Search size={13} aria-hidden />
        <span className="flex-1 truncate max-sm:hidden">Search POs, vendors, clauses…</span>
        <Kbd className="max-sm:hidden">/</Kbd>
        <Kbd className="max-md:hidden">⌘K</Kbd>
      </button>
      {IS_MOCK && (
        <span className="hidden items-center gap-1.5 font-mono text-[10.5px] text-fm-muted lg:flex" title="MSW serves the API from repo data files">
          <span className="h-1.5 w-1.5 rounded-full bg-fm-info" aria-hidden /> REPLAY
        </span>
      )}
    </header>
  );
}
