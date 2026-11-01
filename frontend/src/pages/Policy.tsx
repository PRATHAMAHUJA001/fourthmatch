/** Policy: the controlled document, its compiled rules, and the what-if replay. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ErrorState, Skeleton, SkeletonRows } from "../components/ui/EmptyState";
import { PageHeader, Panel } from "../components/ui/Panel";
import { api } from "../lib/api";
import { formatDate } from "../lib/format";
import { cn } from "../lib/cn";
import type { PolicyClause } from "../types/api";
import { RuleCard } from "./policy/RuleCard";
import { WhatIf } from "./policy/WhatIf";

export function Policy() {
  const qc = useQueryClient();
  const [params] = useSearchParams();
  const focusClause = params.get("clause");
  const policyQ = useQuery({ queryKey: ["policy"], queryFn: api.policy });
  const rulesQ = useQuery({ queryKey: ["rules"], queryFn: api.rules });
  const casesQ = useQuery({ queryKey: ["cases"], queryFn: api.cases });

  const [hover, setHover] = useState<{ clause: string; from: "rule" | "clause" } | null>(null);
  const clauseEls = useRef(new Map<string, HTMLElement>());
  const ruleEls = useRef(new Map<number, HTMLElement>());

  const decide = useMutation({
    mutationFn: ({ id, ok }: { id: number; ok: boolean }) => (ok ? api.approveRule(id) : api.rejectRule(id)),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["rules"] }),
  });

  const rules = useMemo(() => rulesQ.data ?? [], [rulesQ.data]);
  const ruledClauses = useMemo(() => new Set(rules.map((r) => r.source_clause)), [rules]);
  const approved = rules.filter((r) => r.status === "approved").length;
  const pending = rules.filter((r) => r.status === "pending_approval").length;

  const highlighted = hover?.clause ?? focusClause;

  useEffect(() => {
    if (!focusClause || !policyQ.data) return;
    clauseEls.current.get(focusClause)?.scrollIntoView({ block: "center" });
  }, [focusClause, policyQ.data]);

  useEffect(() => {
    if (!hover) return;
    if (hover.from === "rule") clauseEls.current.get(hover.clause)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    else {
      const r = rules.find((x) => x.source_clause === hover.clause);
      if (r) ruleEls.current.get(r.id)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }, [hover, rules]);

  if (policyQ.isError) return <ErrorState message={policyQ.error instanceof Error ? policyQ.error.message : "Could not load the policy."} />;

  const policy = policyQ.data;
  const sections: { name: string; clauses: PolicyClause[] }[] = [];
  for (const c of policy?.clauses ?? []) {
    const last = sections[sections.length - 1];
    if (last && last.name === c.section) last.clauses.push(c); else sections.push({ name: c.section, clauses: [c] });
  }

  return (
    <div className="mx-auto max-w-[1280px]">
      <PageHeader
        eyebrow={policy ? `Policy · ${policy.document_no}` : "Policy"}
        title={policy?.title ?? <Skeleton className="h-6 w-80" />}
        meta={policy && (
          <>
            <span>Version <span className="font-mono text-fm-text">{policy.version}</span></span>
            <span>Effective <span className="font-mono text-fm-text">{formatDate(policy.effective_date)} {policy.effective_date.slice(0, 4)}</span></span>
            <span><span className="font-mono text-fm-text">{policy.clauses.length}</span> clauses</span>
            <span>
              <span className="font-mono text-fm-verified">{approved}</span> rules approved
              {" / "}
              <span className={cn("font-mono", pending > 0 ? "text-fm-hold" : "text-fm-text")}>{pending}</span> pending
            </span>
          </>
        )}
      />

      <div className="mb-4">
        {policy ? <WhatIf policy={policy} caseCount={casesQ.data?.length ?? null} /> : <Skeleton className="h-56 w-full" />}
      </div>

      <div className="grid items-start gap-4 lg:grid-cols-[7fr_5fr]">
        <Panel title="Policy document" subtitle={policy ? `${policy.document_no} · v${policy.version}` : undefined} padded={false}>
          {!policy ? (
            <SkeletonRows rows={8} className="p-3" />
          ) : (
            <div className="px-3 py-2">
              {sections.map((s) => (
                <Fragment key={s.name}>
                  <h3 className="fm-label mt-4 border-b border-fm-border pb-1 first:mt-1">{s.name}</h3>
                  {s.clauses.map((c) => {
                    const has = ruledClauses.has(c.clause_id);
                    const on = highlighted === c.clause_id;
                    return (
                      <div
                        key={c.clause_id}
                        id={`clause-${c.clause_id}`}
                        ref={(el) => { if (el) clauseEls.current.set(c.clause_id, el); else clauseEls.current.delete(c.clause_id); }}
                        onMouseEnter={() => setHover({ clause: c.clause_id, from: "clause" })}
                        onMouseLeave={() => setHover(null)}
                        className={cn(
                          "relative grid grid-cols-[56px_1fr] gap-x-2 border-b border-fm-border py-2 pl-2 pr-2 transition-colors duration-[var(--fm-motion)] last:border-0",
                          on && "bg-fm-hold-bg",
                        )}
                      >
                        {has && <span className="absolute inset-y-1 left-0 w-[2px] bg-fm-hold" aria-hidden />}
                        <span className={cn("pt-px font-mono text-[12px]", has ? "text-fm-hold" : "text-fm-faint")}>§{c.clause_id}</span>
                        <p className="max-w-[68ch] text-[13.5px] leading-[1.55]">{c.text}</p>
                      </div>
                    );
                  })}
                </Fragment>
              ))}
            </div>
          )}
        </Panel>

        <Panel
          title="Compiled rules"
          subtitle={rulesQ.data ? `${rules.length} rules` : undefined}
          padded={false}
          className="lg:sticky lg:top-3 lg:max-h-[calc(100vh-24px)]"
          bodyClassName="fm-scroll overflow-y-auto"
        >
          {rulesQ.isError ? (
            <ErrorState message={rulesQ.error instanceof Error ? rulesQ.error.message : "Could not load rules."} />
          ) : !rulesQ.data ? (
            <SkeletonRows rows={5} className="p-3" />
          ) : (
            <ul>
              {rules.map((r) => (
                <RuleCard
                  key={r.id}
                  rule={r}
                  ref={(el) => { if (el) ruleEls.current.set(r.id, el); else ruleEls.current.delete(r.id); }}
                  active={highlighted === r.source_clause}
                  busy={decide.isPending}
                  onHover={(clause) => setHover(clause ? { clause, from: "rule" } : null)}
                  onApprove={(id) => decide.mutate({ id, ok: true })}
                  onReject={(id) => decide.mutate({ id, ok: false })}
                />
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </div>
  );
}
