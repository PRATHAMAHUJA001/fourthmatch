import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTheme } from "../../lib/theme";
import { NAV } from "./nav";

function isTyping(t: EventTarget | null) {
  const el = t as HTMLElement | null;
  return !!el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT" || el.isContentEditable);
}

/** Global keys: "/" or ⌘K palette, "g 1-5" pages, "t" theme. Returns the palette state. */
export function useGlobalKeys() {
  const [palette, setPalette] = useState(false);
  const navigate = useNavigate();
  const { toggle } = useTheme();
  const gPressed = useRef(0);

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

  return [palette, setPalette] as const;
}
