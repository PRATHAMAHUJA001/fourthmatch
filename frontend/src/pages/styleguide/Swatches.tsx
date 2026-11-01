import { useEffect, useRef } from "react";
import { useTheme } from "../../lib/theme";
import { cssVar } from "../../tokens/tokens";

const SURFACES = ["--fm-canvas", "--fm-bg", "--fm-panel", "--fm-raised", "--fm-hover", "--fm-border", "--fm-border-strong"];
const TEXT = ["--fm-text", "--fm-muted", "--fm-faint", "--fm-accent"];
const SIGNALS = ["--fm-hold", "--fm-verified", "--fm-fraud", "--fm-review", "--fm-info"];
const TINTS = ["--fm-hold-fill", "--fm-verified-fill", "--fm-fraud-fill", "--fm-hold-bg", "--fm-verified-bg"];

/** Resolve any CSS colour (including color-mix) to #rrggbb or rgba() via a canvas. */
function toHex(value: string): string {
  if (!value) return "—";
  try {
    const c = document.createElement("canvas").getContext("2d");
    if (!c) return value;
    c.clearRect(0, 0, 1, 1);
    c.fillStyle = "#000";
    c.fillStyle = value;
    c.fillRect(0, 0, 1, 1);
    const [r, g, b, a] = c.getImageData(0, 0, 1, 1).data;
    const h = (n: number) => n.toString(16).padStart(2, "0");
    return a === 255 ? `#${h(r)}${h(g)}${h(b)}` : `#${h(r)}${h(g)}${h(b)}${h(a)}`;
  } catch {
    return value;
  }
}

function Swatch({ name }: { name: string }) {
  const { theme } = useTheme();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    // Runs after the provider has applied data-theme; reads the live computed value.
    if (ref.current) ref.current.textContent = toHex(cssVar(name));
  }, [theme, name]);
  return (
    <div className="flex items-center gap-2.5">
      <span className="h-9 w-9 shrink-0 rounded-full shadow-[inset_0_0_0_1px_var(--fm-border)]" style={{ background: `var(${name})` }} aria-hidden />
      <div className="min-w-0 leading-tight">
        <div className="truncate font-mono text-[11px] text-fm-text">{name}</div>
        <div ref={ref} className="font-mono text-[11px] text-fm-muted" />
      </div>
    </div>
  );
}

function Group({ title, names }: { title: string; names: string[] }) {
  return (
    <div>
      <div className="fm-label mb-2">{title}</div>
      <div className="grid gap-x-4 gap-y-2.5 sm:grid-cols-2 xl:grid-cols-1">
        {names.map((n) => <Swatch key={n} name={n} />)}
      </div>
    </div>
  );
}

export function ColourTokens() {
  return (
    <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
      <Group title="Surfaces" names={SURFACES} />
      <Group title="Text" names={TEXT} />
      <Group title="Signals" names={SIGNALS} />
      <Group title="Fills & tints" names={TINTS} />
    </div>
  );
}
