/** Line-art trailer with one slot per invoiced unit. Units seen on the dock video are
 *  drawn solid; units nobody saw are dashed gaps; damaged units are cross-hatched.
 *  Counts come from props (SAM tracks / documents); this only draws them. */
import { cn } from "../../lib/cn";

interface Props {
  invoiced: number;
  observed: number;
  damaged?: number;
  unit?: string;
  /** "ink" draws in dark ink for use on the amber block. */
  tone?: "default" | "ink";
  className?: string;
  label?: string;
}

const W = 600;
const H = 200;
const TX = 8, TY = 14, TW = 432, TH = 128; // trailer box

export function LoadDiagram({ invoiced, observed, damaged = 0, unit = "unit", tone = "default", className, label }: Props) {
  const n = Math.max(1, Math.min(invoiced, 120));
  const rows = n <= 6 ? 1 : n <= 16 ? 2 : n <= 45 ? 3 : 4;
  const cols = Math.ceil(n / rows);
  const pad = 10;
  const gap = n > 40 ? 3 : 6;
  const cw = (TW - pad * 2 - gap * (cols - 1)) / cols;
  const ch = Math.min((TH - pad * 2 - gap * (rows - 1)) / rows, cw * 0.78);
  const ink = tone === "ink" ? "var(--fm-ink-fixed, #16171a)" : "var(--fm-text)";
  const faint = tone === "ink" ? "rgba(22,23,26,0.45)" : "var(--fm-faint)";
  const miss = tone === "ink" ? "#16171a" : "var(--fm-hold)";
  const seen = Math.min(observed, n);
  const missing = Math.max(0, invoiced - observed);
  const cells = Array.from({ length: n }, (_, i) => {
    // fill bottom-up, left to right, like a loaded trailer
    const r = rows - 1 - Math.floor(i / cols);
    const c = i % cols;
    const x = TX + pad + c * (cw + gap);
    const y = TY + TH - pad - ch - (rows - 1 - r) * (ch + gap);
    const state = i < seen - damaged ? "ok" : i < seen ? "damaged" : "missing";
    return { i, x, y, state };
  });
  const aria = label ?? `${invoiced} ${unit} invoiced, ${observed} seen on video${missing ? `, ${missing} missing` : ""}${damaged ? `, ${damaged} damaged` : ""}`;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className={cn("w-full", className)} role="img" aria-label={aria}>
      <defs>
        <pattern id="fm-hatch" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <line x1="0" y1="0" x2="0" y2="5" stroke={miss} strokeWidth="1.4" />
        </pattern>
      </defs>
      {/* trailer */}
      <rect x={TX} y={TY} width={TW} height={TH} fill="none" stroke={ink} strokeWidth="1.6" rx="2" />
      <line x1={TX} y1={TY + TH + 8} x2={TX + TW + 6} y2={TY + TH + 8} stroke={ink} strokeWidth="1.6" />
      <line x1={TX + 30} y1={TY + TH} x2={TX + 30} y2={TY + TH + 8} stroke={ink} strokeWidth="1.2" />
      {/* landing leg */}
      <line x1={TX + 200} y1={TY + TH + 8} x2={TX + 200} y2={TY + TH + 30} stroke={ink} strokeWidth="1.4" />
      <line x1={TX + 194} y1={TY + TH + 30} x2={TX + 206} y2={TY + TH + 30} stroke={ink} strokeWidth="1.4" />
      {/* cab */}
      <path
        d={`M${TX + TW + 12} ${TY + TH + 8} V${TY + 40} H${TX + TW + 78} L${TX + TW + 112} ${TY + 78} H${TX + TW + 140} V${TY + TH + 8} Z`}
        fill="none" stroke={ink} strokeWidth="1.6" strokeLinejoin="round"
      />
      <path d={`M${TX + TW + 82} ${TY + 50} L${TX + TW + 104} ${TY + 78} H${TX + TW + 82} Z`} fill="none" stroke={ink} strokeWidth="1.2" />
      {Array.from({ length: 4 }, (_, k) => (
        <line key={k} x1={TX + TW + 22} y1={TY + 52 + k * 8} x2={TX + TW + 62} y2={TY + 52 + k * 8} stroke={faint} strokeWidth="1" />
      ))}
      <rect x={TX + TW + 140} y={TY + TH - 14} width="10" height="16" fill="none" stroke={ink} strokeWidth="1.2" />
      {/* wheels */}
      {[TX + 40, TX + 82, TX + 124, TX + TW + 36, TX + TW + 112].map((cx) => (
        <g key={cx}>
          <circle cx={cx} cy={TY + TH + 22} r="15" fill={tone === "ink" ? "transparent" : "var(--fm-panel)"} stroke={ink} strokeWidth="1.6" />
          <circle cx={cx} cy={TY + TH + 22} r="6" fill="none" stroke={ink} strokeWidth="1.2" />
        </g>
      ))}
      {/* cargo */}
      {cells.map(({ i, x, y, state }) => (
        <g key={i}>
          {state === "missing" ? (
            <rect x={x} y={y} width={cw} height={ch} rx="1.5" fill="none" stroke={miss} strokeWidth="1.4" strokeDasharray="4 3" />
          ) : (
            <>
              <rect x={x} y={y} width={cw} height={ch} rx="1.5" fill={state === "damaged" ? "url(#fm-hatch)" : "none"} stroke={state === "damaged" ? miss : ink} strokeWidth="1.3" />
              {cw > 14 && <line x1={x + cw / 2} y1={y} x2={x + cw / 2} y2={y + ch * 0.32} stroke={state === "damaged" ? miss : faint} strokeWidth="1.2" />}
            </>
          )}
        </g>
      ))}
    </svg>
  );
}
