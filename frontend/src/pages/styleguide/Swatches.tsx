import { useEffect, useRef } from "react";
import { useTheme } from "../../lib/theme";
import { cssVar } from "../../tokens/tokens";

const SURFACES = ["--fm-bg", "--fm-sunken", "--fm-panel", "--fm-raised", "--fm-hover", "--fm-border", "--fm-border-strong"];
const TEXT = ["--fm-text", "--fm-muted", "--fm-faint"];
const SIGNALS = ["--fm-hold", "--fm-verified", "--fm-fraud", "--fm-review", "--fm-info"];
const TINTS = ["--fm-hold-bg", "--fm-verified-bg", "--fm-fraud-bg", "--fm-review-bg", "--fm-info-bg"];

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
      <span className="h-8 w-8 shrink-0 rounded-fm-sm border border-fm-border-strong" style={{ background: `var(${name})` }} aria-hidden />
      <div className="min-w-0 leading-tight">
        <div className="truncate font-mono text-[11px] text-fm-text">{name}</div>
        <div ref={ref} className="font-mono text-[10.5px] uppercase text-fm-muted" />
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
      <Group title="Signal tints" names={TINTS} />
    </div>
  );
}
