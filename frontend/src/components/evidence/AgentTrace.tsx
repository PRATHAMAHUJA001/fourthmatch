import { ChevronRight } from "lucide-react";
import { useState } from "react";
import { cn } from "../../lib/cn";
import type { AgentStep } from "../../types/api";

function Json({ value }: { value: unknown }) {
  return (
    <pre className="fm-scroll max-h-48 overflow-auto whitespace-pre-wrap break-all rounded-[3px] border border-fm-border bg-fm-sunken p-2 font-mono text-[11px] leading-relaxed text-fm-muted">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

const TOOL_TONE: Record<string, string> = {
  record_decision: "text-fm-hold",
  draft_debit_note: "text-fm-hold",
  evaluate_rule: "text-fm-text",
  compute_variance: "text-fm-text",
};

/** Every tool call the decision agent made, in order. Numbers come from tools, never the model. */
export function AgentTrace({ steps }: { steps: AgentStep[] }) {
  const [open, setOpen] = useState<number | null>(null);
  const total = steps.reduce((s, x) => s + (x.latency_ms ?? 0), 0);
  return (
    <div>
      <ol className="flex flex-col">
        {steps.map((s) => {
          const fired = s.tool === "evaluate_rule" ? Boolean((s.result as { fired?: boolean }).fired) : null;
          const isOpen = open === s.seq;
          return (
            <li key={s.seq} className="border-b border-fm-border last:border-0">
              <button
                type="button"
                onClick={() => setOpen(isOpen ? null : s.seq)}
                aria-expanded={isOpen}
                className="flex h-8 w-full items-center gap-2.5 px-1 text-left hover:bg-fm-hover"
              >
                <span className="w-5 shrink-0 text-right font-mono text-[10.5px] text-fm-faint">{String(s.seq).padStart(2, "0")}</span>
                <ChevronRight size={12} className={cn("shrink-0 text-fm-faint transition-transform", isOpen && "rotate-90")} />
                <span className={cn("font-mono text-[12px]", TOOL_TONE[s.tool] ?? "text-fm-muted")}>{s.tool}</span>
                <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-fm-faint">
                  ({Object.entries(s.args).map(([k, v]) => `${k}=${typeof v === "string" ? v : JSON.stringify(v)}`).join(", ")})
                </span>
                {fired !== null && (
                  <span className={cn("font-cond text-[10px] font-semibold uppercase tracking-[0.08em]", fired ? "text-fm-hold" : "text-fm-faint")}>{fired ? "fired" : "pass"}</span>
                )}
                <span className="w-12 shrink-0 text-right font-mono text-[10.5px] tabular-nums text-fm-faint">{s.latency_ms != null ? `${s.latency_ms}ms` : "—"}</span>
              </button>
              {isOpen && (
                <div className="grid gap-2 px-8 pb-3 pt-1 md:grid-cols-2">
                  <div><div className="fm-label mb-1">Input</div><Json value={s.args} /></div>
                  <div><div className="fm-label mb-1">Output</div><Json value={s.result} /></div>
                </div>
              )}
            </li>
          );
        })}
      </ol>
      <div className="mt-2 flex items-center justify-between px-1 font-mono text-[10.5px] text-fm-faint">
        <span>{steps.length} tool calls · 0 numbers produced by the model</span>
        <span className="tabular-nums">Σ {total} ms tools</span>
      </div>
    </div>
  );
}
