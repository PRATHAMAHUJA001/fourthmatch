import * as Dialog from "@radix-ui/react-dialog";
import { Menu, Moon, Search, Sun, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { cn } from "../../lib/cn";
import { useTheme } from "../../lib/theme";
import { Kbd } from "../ui/Tag";
import { BrandMark } from "./BrandMark";
import { NAV } from "./nav";

/** Scroll state for the nav: past the threshold, and whether a dark section ([data-nav-dark])
 *  sits under the bar. Measured once per animation frame. */
function useNavScroll(threshold: number) {
  const [state, setState] = useState({ past: false, dark: false });
  useEffect(() => {
    let raf = 0;
    const measure = () => {
      raf = 0;
      const y = 26;
      let dark = false;
      document.querySelectorAll<HTMLElement>("[data-nav-dark]").forEach((el) => {
        const r = el.getBoundingClientRect();
        if (r.top <= y && r.bottom >= y) dark = true;
      });
      const past = window.scrollY > threshold;
      setState((s) => (s.past === past && s.dark === dark ? s : { past, dark }));
    };
    const on = () => { if (!raf) raf = requestAnimationFrame(measure); };
    measure();
    window.addEventListener("scroll", on, { passive: true });
    window.addEventListener("resize", on);
    // Scroll-driven sections toggle [data-nav-dark] during React renders that land after the
    // scroll frame was measured (the sticky story's camera chapter). Re-measure whenever the
    // attribute changes, and once scrolling settles (iOS momentum), so the bar never stays dark
    // over a white section.
    const mo = typeof MutationObserver !== "undefined" ? new MutationObserver(on) : null;
    mo?.observe(document.body, { attributes: true, attributeFilter: ["data-nav-dark"], subtree: true, childList: true });
    window.addEventListener("scrollend", on);
    return () => {
      window.removeEventListener("scroll", on); window.removeEventListener("resize", on); window.removeEventListener("scrollend", on);
      mo?.disconnect(); cancelAnimationFrame(raf);
    };
  }, [threshold]);
  return state;
}

function SyntheticPill({ onDark }: { onDark?: boolean }) {
  return (
    <span
      title="Every vendor, PO, invoice and video in this product is synthetic."
      className={cn(
        "inline-flex h-6 shrink-0 items-center gap-1.5 rounded-full px-2.5 text-[12px] font-medium tracking-[-0.005em]",
        onDark ? "bg-white/15 text-white" : "bg-fm-hold-bg text-fm-hold",
      )}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-fm-hold-fill" aria-hidden />
      Synthetic data
    </span>
  );
}

/** Frosted sticky top navigation. `overlay` starts transparent with white text over a dark hero
 *  and turns into frosted glass once the hero has scrolled away. */
export function TopNav({ onOpenPalette, overlay, wide }: { onOpenPalette: () => void; overlay?: boolean; /** Match the app content width (1440) instead of the landing column (1200). */ wide?: boolean }) {
  const { theme, toggle } = useTheme();
  const [menu, setMenu] = useState(false);
  const { pathname } = useLocation();
  const [threshold, setThreshold] = useState(8);
  useEffect(() => {
    if (!overlay) return;
    const set = () => setThreshold(Math.max(8, window.innerHeight - 80));
    set();
    window.addEventListener("resize", set);
    return () => window.removeEventListener("resize", set);
  }, [overlay]);
  const { past: scrolled, dark: overDark } = useNavScroll(threshold);
  const transparent = !!overlay && !scrolled;
  /** White text: transparent over the hero, or dark glass over a dark section. */
  const onDark = transparent || overDark;
  useEffect(() => setMenu(false), [pathname]);

  const linkCls = (active: boolean) => cn(
    "rounded-full px-3 py-1.5 text-[13px] tracking-[-0.01em] transition-colors duration-200",
    onDark ? (active ? "text-white" : "text-white/75 hover:text-white") : (active ? "text-fm-text font-medium" : "text-fm-muted hover:text-fm-text"),
  );
  const iconBtn = cn(
    "flex h-9 w-9 items-center justify-center rounded-full transition-colors duration-200",
    onDark ? "text-white/85 hover:bg-white/15 hover:text-white" : "text-fm-muted hover:bg-fm-raised hover:text-fm-text",
  );

  return (
    <header
      className={cn(
        "sticky top-0 z-40 transition-[background-color,box-shadow,color] duration-300 ease-[var(--fm-ease)]",
        overlay && "-mb-[var(--fm-nav-h)]",
        transparent ? "bg-transparent text-white" : onDark ? "fm-glass-dark text-white" : "fm-glass text-fm-text shadow-[inset_0_-1px_0_var(--fm-glass-line)]",
      )}
    >
      <nav aria-label="Primary" className={cn("mx-auto flex h-[var(--fm-nav-h)] items-center gap-1", wide ? "max-w-[1440px] px-4 sm:px-6 lg:px-8" : "max-w-[1200px] px-6")}>
        <Link to="/" aria-label="FourthMatch home" className="mr-4 flex items-center gap-2 rounded-full py-1">
          <BrandMark size={18} />
          <span className="text-[17px] font-semibold tracking-[-0.025em]">FourthMatch</span>
        </Link>
        <div className="hidden items-center md:flex">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} className={({ isActive }) => linkCls(isActive)} title={`${n.label} · g ${n.key}`}>
              {n.short}
            </NavLink>
          ))}
        </div>
        <div className="ml-auto flex items-center gap-1">
          <span className="mr-1 hidden lg:inline-flex"><SyntheticPill onDark={onDark} /></span>
          <button
            type="button"
            onClick={onOpenPalette}
            aria-label="Global search"
            className={cn(
              "flex h-9 items-center gap-2 rounded-full transition-colors duration-200 max-sm:w-9 max-sm:justify-center sm:pl-3 sm:pr-2",
              onDark ? "text-white/85 hover:bg-white/15" : "text-fm-muted hover:bg-fm-raised hover:text-fm-text",
            )}
          >
            <Search size={16} strokeWidth={1.8} aria-hidden />
            <span className="hidden text-[13px] sm:inline">Search</span>
            <Kbd className={cn("hidden sm:inline-flex", onDark && "bg-white/15 text-white shadow-none")}>/</Kbd>
          </button>
          <button type="button" onClick={toggle} className={iconBtn} aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"} title="Theme · t">
            {theme === "dark" ? <Sun size={16} strokeWidth={1.8} /> : <Moon size={16} strokeWidth={1.8} />}
          </button>
          <Dialog.Root open={menu} onOpenChange={setMenu}>
            <Dialog.Trigger asChild>
              <button type="button" className={cn(iconBtn, "md:hidden")} aria-label="Open menu"><Menu size={18} strokeWidth={1.8} /></button>
            </Dialog.Trigger>
            <Dialog.Portal>
              <Dialog.Overlay className="fixed inset-0 z-50 bg-black/30" />
              <Dialog.Content className="fm-glass fixed inset-x-0 top-0 z-50 rounded-b-fm-xl px-6 pb-8 pt-3 text-fm-text shadow-fm-float" aria-describedby={undefined}>
                <Dialog.Title className="sr-only">Menu</Dialog.Title>
                <div className="flex h-10 items-center justify-between">
                  <span className="flex items-center gap-2"><BrandMark size={18} /><span className="text-[17px] font-semibold tracking-[-0.025em]">FourthMatch</span></span>
                  <Dialog.Close className="flex h-9 w-9 items-center justify-center rounded-full text-fm-muted hover:bg-fm-raised" aria-label="Close menu"><X size={18} /></Dialog.Close>
                </div>
                <ul className="mt-4 flex flex-col">
                  {NAV.map((n) => (
                    <li key={n.to}>
                      <NavLink to={n.to} className={({ isActive }) => cn("block border-b border-fm-border py-3 text-[28px] font-semibold tracking-[-0.03em]", isActive ? "text-fm-text" : "text-fm-muted")}>
                        {n.label}
                      </NavLink>
                    </li>
                  ))}
                </ul>
                <div className="mt-6"><SyntheticPill /></div>
              </Dialog.Content>
            </Dialog.Portal>
          </Dialog.Root>
        </div>
      </nav>
    </header>
  );
}
