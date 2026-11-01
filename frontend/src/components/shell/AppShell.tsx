import { useEffect, useRef } from "react";
import { Outlet } from "react-router-dom";
import { Rail } from "./Rail";
import { TopBar } from "./TopBar";

export function AppShell() {
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const target = e.target as HTMLElement;
      const typing = target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable;
      if (e.key === "/" && !typing) {
        e.preventDefault();
        searchRef.current?.focus();
      }
      if (e.key === "Escape" && document.activeElement === searchRef.current) {
        searchRef.current?.blur();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="flex h-full flex-col bg-fm-bg text-fm-text">
      <TopBar ref={searchRef} />
      <div className="flex min-h-0 flex-1">
        <Rail />
        <main className="fm-scroll min-w-0 flex-1 overflow-auto p-4">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
