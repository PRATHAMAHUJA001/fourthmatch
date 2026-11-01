import { useEffect, useRef, useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { useTheme } from "../../lib/theme";
import { CommandPalette } from "./CommandPalette";
import { NAV } from "./nav";
import { Rail } from "./Rail";
import { StatusBar } from "./StatusBar";
import { TopBar } from "./TopBar";

function isTyping(t: EventTarget | null) {
  const el = t as HTMLElement | null;
  return !!el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT" || el.isContentEditable);
}

/** Global keys: "/" or ⌘K palette, "g 1-5" pages, "t" theme. */
export function AppShell() {
  const [palette, setPalette] = useState(false);
  const navigate = useNavigate();
  const { toggle } = useTheme();
  const gPressed = useRef(0);
  const { pathname } = useLocation();
  const mainRef = useRef<HTMLElement>(null);

  useEffect(() => { mainRef.current?.scrollTo({ top: 0 }); }, [pathname]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setPalette((p) => !p); return; }
      if (isTyping(e.target) || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "/") { e.preventDefault(); setPalette(true); return; }
      if (e.key === "g") { gPressed.current = Date.now(); return; }
      if (Date.now() - gPressed.current < 900) {
        const n = NAV.find((x) => x.key === e.key);
        if (n) { e.preventDefault(); navigate(n.to); }
        gPressed.current = 0;
        return;
      }
      if (e.key === "t") toggle();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [navigate, toggle]);

  return (
    <div className="flex h-full flex-col bg-fm-bg text-fm-text">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:bg-fm-panel focus:px-2 focus:py-1">Skip to content</a>
      <TopBar onOpenPalette={() => setPalette(true)} />
      <div className="flex min-h-0 flex-1">
        <Rail />
        <main id="main" ref={mainRef} className="fm-scroll min-w-0 flex-1 overflow-auto">
          <div key={pathname} className="fm-rise mx-auto w-full max-w-[1480px] px-4 py-4 sm:px-5 sm:py-5">
            <Outlet />
          </div>
        </main>
      </div>
      <StatusBar />
      <CommandPalette open={palette} onOpenChange={setPalette} />
    </div>
  );
}
