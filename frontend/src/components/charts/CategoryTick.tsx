import { chartTheme } from "../../tokens/tokens";

/** Right-aligned category tick that never wraps (labels are pre-truncated). */
export function CategoryTick({ x, y, payload }: { x?: number; y?: number; payload?: { value: string } }) {
  const t = chartTheme();
  return (
    <text x={(x ?? 0) - 4} y={y} dy={3.5} textAnchor="end" fill={t.tick} fontSize={10.5} fontFamily="var(--fm-font-mono)">
      {payload?.value}
    </text>
  );
}
