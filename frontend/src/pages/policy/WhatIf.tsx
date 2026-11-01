import { useMutation } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";
import { useState } from "react";
import { Button } from "../../components/ui/Button";
import { ErrorState } from "../../components/ui/EmptyState";
import { Money } from "../../components/ui/Money";
import { Panel } from "../../components/ui/Panel";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { api } from "../../lib/api";
import { cn } from "../../lib/cn";
import { formatINR } from "../../lib/format";
import type { PolicyRead } from "../../types/api";

export function WhatIf({ policy, caseCount }: { policy: PolicyRead; caseCount: number | null }) {
  const [clauseId, setClauseId] = useState(() => (policy.clauses.some((c) => c.clause_id === "4.2") ? "4.2" : policy.clauses[0]?.clause_id ?? ""));
  const original = policy.clauses.find((c) => c.clause_id === clauseId)?.text ?? "";
  const [text, setText] = useState(original);

  const sim = useMutation({ mutationFn: () => api.simulate(policy.id, clauseId, text) });
  const dirty = text !== original;
  const result = sim.data;
  const delta = result ? result.held_after_paise - result.held_before_paise : 0;

  function reset() { setText(original); sim.reset(); }

  return (
    <Panel
      title="What if the policy changed?"
      subtitle="Edit one clause and replay every past decision against the draft."
      bodyClassName="grid gap-8 lg:grid-cols-[5fr_7fr]"
    >
      <div className="flex min-w-0 flex-col gap-3">
        <label className="flex items-center gap-3">
          <span className="shrink-0 text-[13px] font-semibold text-fm-muted">Clause</span>
          <select
            value={clauseId}
            onChange={(e) => { setClauseId(e.target.value); setText(policy.clauses.find((c) => c.clause_id === e.target.value)?.text ?? ""); sim.reset(); }}
            className="fm-field h-10 min-w-0 flex-1 px-3 text-[14px]"
          >
            {policy.clauses.map((c) => (
              <option key={c.clause_id} value={c.clause_id}>§{c.clause_id} · {c.section}</option>
            ))}
          </select>
        </label>
        <textarea
          aria-label="Draft clause text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={8}
          spellCheck={false}
          className="fm-field fm-scroll w-full resize-y p-4 text-[15px] leading-relaxed"
        />
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="accent" size="lg" disabled={sim.isPending || !text.trim()} onClick={() => sim.mutate()}>
            Run replay
          </Button>
          <Button variant="ghost" size="lg" disabled={!dirty && !result && !sim.isError} onClick={reset}>Reset</Button>
          {dirty && <span className="text-[13px] font-medium text-fm-hold">Draft edited</span>}
        </div>
        <p className="text-[12px] text-fm-faint">Draft rules are never saved. Replay re-runs past decisions against the draft only.</p>
      </div>

      <div className="min-w-0 rounded-fm bg-fm-raised p-6 max-sm:p-5">
        {sim.isPending ? (
          <div role="status" className="flex h-full min-h-32 flex-col justify-center gap-2">
            <div className="h-1 w-full overflow-hidden rounded-full bg-fm-hover"><div className="fm-live-dot h-1 w-1/3 rounded-full bg-fm-accent" /></div>
            <p className="text-[14px] text-fm-muted">
              Compiling draft clause · re-evaluating {caseCount ?? "all"} past cases
            </p>
          </div>
        ) : sim.isError ? (
          <ErrorState message={sim.error instanceof Error ? sim.error.message : "Replay failed."} />
        ) : result ? (
          <div className="fm-rise flex flex-col gap-3">
            <div className="flex flex-wrap items-end gap-x-6 gap-y-2">
              <div>
                <div className="mb-2 text-[13px] font-semibold text-fm-muted">Rupees held</div>
                <div className="fm-appear flex flex-wrap items-center gap-3 leading-none">
                  <span className="fm-figure text-[32px] text-fm-muted">{formatINR(result.held_before_paise)}</span>
                  <ArrowRight size={22} className="text-fm-faint" aria-hidden />
                  <span className="fm-figure text-[44px]">{formatINR(result.held_after_paise)}</span>
                </div>
              </div>
              <div>
                <div className="mb-2 text-[13px] font-semibold text-fm-muted">Change</div>
                <Money
                  paise={delta}
                  sign
                  className={cn("text-[19px] font-medium", delta < 0 ? "!text-fm-verified" : delta > 0 ? "!text-fm-hold" : "!text-fm-muted")}
                />
              </div>
              <div className="ml-auto text-right text-[12px] text-fm-faint">
                <span className="font-mono">{result.draft_policy_version}</span><br />
                <span className="font-mono">{result.unchanged_count}</span> unchanged
              </div>
            </div>

            {result.changed.length === 0 ? (
              <p className="border-t border-fm-border pt-4 text-[14px] text-fm-muted">No past verdict changes under this draft.</p>
            ) : (
              <div className="fm-scroll overflow-x-auto border-t border-fm-border">
                <table className="w-full border-collapse text-[13px]">
                  <thead>
                    <tr className="text-left">
                      {["PO", "Vendor", "Verdict", "Held"].map((h, i) => (
                        <th key={h} className={cn("h-10 whitespace-nowrap pr-3 text-[12px] font-semibold text-fm-muted", i === 3 && "text-right")}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {result.changed.map((d) => (
                      <tr key={d.po_number} className="border-t border-fm-border">
                        <td className="h-11 whitespace-nowrap pr-3 font-mono text-[12.5px]">{d.po_number}</td>
                        <td className="max-w-[160px] truncate pr-3">{d.vendor_name}</td>
                        <td className="whitespace-nowrap pr-3">
                          <span className="inline-flex items-center gap-1.5">
                            <StatusBadge verdict={d.before} size="sm" />
                            <ArrowRight size={12} className="text-fm-faint" aria-hidden />
                            <StatusBadge verdict={d.after} size="sm" />
                          </span>
                        </td>
                        <td className="whitespace-nowrap text-right">
                          <Money paise={d.held_before_paise} muted />
                          <span className="mx-1.5 text-fm-faint" aria-hidden>→</span>
                          <Money paise={d.held_after_paise} className={d.held_after_paise > d.held_before_paise ? "text-fm-hold" : d.held_after_paise < d.held_before_paise ? "text-fm-verified" : undefined} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        ) : (
          <div className="flex h-full min-h-40 flex-col justify-center gap-2">
            <p className="text-[21px] font-semibold tracking-[-0.02em]">Edit the clause, then run the replay.</p>
            <p className="text-[15px] text-fm-muted">Try changing the tolerance for bagged material to 40.0%.</p>
          </div>
        )}
      </div>
    </Panel>
  );
}
