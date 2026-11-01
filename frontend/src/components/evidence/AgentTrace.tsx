import { ChevronRight } from "lucide-react";
import { useState } from "react";
import { cn } from "../../lib/cn";
import type { AgentStep } from "../../types/api";
import { SignalGlyph } from "../ui/Glyph";

function Json({ value }: { value: unknown }) {
  return (
    <pre className="fm-scroll max-h-56 overflow-auto whitespace-pre-wrap break-all rounded-[12px] bg-fm-raised p-3 font-mono text-[12px] leading-relaxed text-fm-muted">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

const argText = (args: Record<string, unknown>) =>
  Object.entries(args).map(([k, v]) => `${k}=${typeof v === "string" ? v : JSON.stringify(v)}`).join(", ");

/** Every tool call the decision agent made, in order, as a disclosure list. Numbers come from
 *  tools, never the model. */
export function AgentTrace({ steps }: { steps: AgentStep[] }) {
  const [open, setOpen] = useState<number | null>(null);
  const measured = steps.some((x) => x.latency_ms != null);
  const total = steps.reduce((s, x) => s + (x.latency_ms ?? 0), 0);
  return (
    <div>
      <ol className="flex flex-col">
        {steps.map((s) => {
          const fired = s.tool === "evaluate_rule" ? Boolean((s.result as { fired?: boolean }).fired) : null;
          const decisive = s.tool === "record_decision" || s.tool === "draft_debit_note";
          const isOpen = open === s.seq;
          return (
            <li key={s.seq} className="border-b border-fm-border last:border-0">
              <button
                type="button"
                onClick={() => setOpen(isOpen ? null : s.seq)}
                aria-expanded={isOpen}
                className="-mx-2 flex min-h-12 w-[calc(100%+16px)] items-center gap-3 rounded-[10px] px-2 text-left transition-colors hover:bg-fm-raised"
              >
                <span className="w-5 shrink-0 text-right text-[12px] tabular-nums text-fm-faint">{s.seq}</span>
                <span className="min-w-0 flex-1">
                  <span className={cn("block truncate font-mono text-[13px]", decisive ? "font-medium text-fm-text" : "text-fm-text")}>{s.tool}</span>
                  <span className="block truncate font-mono text-[11.5px] text-fm-faint max-sm:hidden">{argText(s.args)}</span>
                </span>
                {fired !== null && (
                  <span className={cn("flex shrink-0 items-center gap-1.5 text-[12px] font-semibold", fired ? "text-fm-hold" : "text-fm-faint")}>
                    {fired && <SignalGlyph signal="hold" size={11} />}{fired ? "Fired" : "Pass"}
                  </span>
                )}
                {measured && <span className="w-14 shrink-0 text-right font-mono text-[12px] tabular-nums text-fm-faint">{s.latency_ms != null ? `${s.latency_ms} ms` : "—"}</span>}
                <ChevronRight size={15} className={cn("shrink-0 text-fm-faint transition-transform duration-200", isOpen && "rotate-90")} aria-hidden />
              </button>
              {isOpen && (
                <div className="fm-rise grid gap-3 pb-4 pl-8 pt-1 md:grid-cols-2">
                  <div><div className="fm-label mb-1.5">Input</div><Json value={s.args} /></div>
                  <div><div className="fm-label mb-1.5">Output</div><Json value={s.result} /></div>
                </div>
              )}
            </li>
          );
        })}
      </ol>
      <p className="mt-4 flex flex-wrap items-center justify-between gap-2 text-[13px] text-fm-muted">
        <span>{steps.length} tool calls. Every number came from a tool, none from the model.</span>
        {measured && <span className="font-mono tabular-nums text-fm-faint">{total} ms in tools</span>}
      </p>
    </div>
  );
}
