import { chartTheme } from "../../tokens/tokens";

/** Right-aligned category tick that never wraps (labels are pre-truncated). */
export function CategoryTick({ x, y, payload }: { x?: number; y?: number; payload?: { value: string } }) {
  const t = chartTheme();
  return (
    <text x={(x ?? 0) - 10} y={y} dy={4} textAnchor="end" fill={t.text} fontSize={13} fontFamily="var(--fm-font-sans)" letterSpacing="-0.01em">
      {payload?.value}
    </text>
  );
}
