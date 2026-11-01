import { useEffect } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { CommandPalette } from "./CommandPalette";
import { StatusBar } from "./StatusBar";
import { TopNav } from "./TopNav";
import { useGlobalKeys } from "./useGlobalKeys";

/** App frame: frosted top nav, page content on the grey canvas, slim model status bar. */
export function AppShell() {
  const [palette, setPalette] = useGlobalKeys();
  const { pathname } = useLocation();

  useEffect(() => { window.scrollTo({ top: 0 }); }, [pathname]);

  return (
    <div className="flex min-h-screen flex-col bg-fm-bg text-fm-text">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded-full focus:bg-fm-panel focus:px-4 focus:py-2 focus:shadow-fm-float">Skip to content</a>
      <TopNav wide onOpenPalette={() => setPalette(true)} />
      <main id="main" className="min-w-0 flex-1">
        <div key={pathname} className="fm-rise mx-auto w-full max-w-[1440px] px-4 pb-16 pt-6 sm:px-6 sm:pt-8 lg:px-8">
          <Outlet />
        </div>
      </main>
      <StatusBar />
      <CommandPalette open={palette} onOpenChange={setPalette} />
    </div>
  );
}
