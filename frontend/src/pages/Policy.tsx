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
    <div>
      <PageHeader
        eyebrow={policy ? `Policy ${policy.document_no}` : "Policy"}
        title={policy?.title ?? <Skeleton className="h-12 w-96 max-w-full" />}
        meta={policy && (
          <>
            <span>Version {policy.version}, effective {formatDate(policy.effective_date)} {policy.effective_date.slice(0, 4)}</span>
            <span>{policy.clauses.length} clauses</span>
            <span>
              <span className="text-fm-verified">{approved} rules approved</span>
              {pending > 0 && <>, <span className="text-fm-hold">{pending} pending</span></>}
            </span>
          </>
        )}
      />

      <div className="mb-6">
        {policy ? <WhatIf policy={policy} caseCount={casesQ.data?.length ?? null} /> : <Skeleton className="h-72 w-full rounded-fm" />}
      </div>

      <div className="grid items-start gap-6 lg:grid-cols-[7fr_5fr]">
        <Panel title="The document" subtitle="Hover a clause to find the rule compiled from it." padded={false}>
          {!policy ? (
            <SkeletonRows rows={8} className="p-6" />
          ) : (
            <div className="px-4 pb-6 pt-2 max-sm:px-2">
              {sections.map((s) => (
                <Fragment key={s.name}>
                  <h3 className="mx-3 mb-1 mt-8 text-[21px] font-semibold tracking-[-0.02em] first:mt-4">{s.name}</h3>
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
                          "grid scroll-mt-24 grid-cols-[52px_1fr] gap-x-3 rounded-[14px] px-3 py-3 transition-colors duration-200 max-sm:grid-cols-[44px_1fr]",
                          on ? "bg-fm-hold-bg" : has && "hover:bg-fm-raised/70",
                        )}
                      >
                        <span className={cn("pt-px text-[15px] font-semibold tabular-nums", has ? "text-fm-text" : "text-fm-faint")}>
                          {c.clause_id}
                          {has && <span className="ml-1 inline-block h-1.5 w-1.5 -translate-y-0.5 rounded-full bg-fm-hold-fill align-middle" title="A rule is compiled from this clause" aria-label="has a compiled rule" />}
                        </span>
                        <p className={cn("max-w-[68ch] text-[15px] leading-[1.6]", has ? "text-fm-text" : "text-fm-muted")}>{c.text}</p>
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
          subtitle={rulesQ.data ? `${rules.length} rules, each approved by a person before it can fire` : undefined}
          padded={false}
          className="lg:sticky lg:top-[calc(var(--fm-nav-h)+24px)] lg:max-h-[calc(100vh-var(--fm-nav-h)-48px)]"
          bodyClassName="fm-scroll overflow-y-auto px-2 pb-2 pt-2"
        >
          {rulesQ.isError ? (
            <ErrorState message={rulesQ.error instanceof Error ? rulesQ.error.message : "Could not load rules."} />
          ) : !rulesQ.data ? (
            <SkeletonRows rows={5} className="p-4" />
          ) : (
            <ul className="flex flex-col gap-0.5">
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
