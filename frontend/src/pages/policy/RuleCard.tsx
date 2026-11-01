import { AlertTriangle, Check, X } from "lucide-react";
import { forwardRef } from "react";
import { Button } from "../../components/ui/Button";
import type { Signal } from "../../components/ui/Glyph";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { Tag } from "../../components/ui/Tag";
import { cn } from "../../lib/cn";
import type { RuleRead } from "../../types/api";

const ACTION: Record<string, { signal: Signal; label: string }> = {
  hold: { signal: "hold", label: "Hold" },
  partial_pay: { signal: "partial", label: "Partial pay" },
  approve: { signal: "verified", label: "Approve" },
  require_signoff: { signal: "review", label: "Require sign-off" },
};

const STATUS: Record<string, { text: string; cls: string }> = {
  approved: { text: "Approved", cls: "text-fm-verified" },
  pending_approval: { text: "Pending approval", cls: "text-fm-hold" },
  rejected: { text: "Rejected", cls: "text-fm-fraud" },
};

function conditionText(rule: RuleRead): string | null {
  const c = rule.condition;
  if (!c) return null;
  const v = typeof c.value === "string" ? c.value : String(c.value);
  return `${c.field} ${c.op} ${v}`;
}

interface Props {
  rule: RuleRead;
  active: boolean;
  busy: boolean;
  onHover: (clauseId: string | null) => void;
  onApprove: (id: number) => void;
  onReject: (id: number) => void;
}

export const RuleCard = forwardRef<HTMLLIElement, Props>(function RuleCard({ rule, active, busy, onHover, onApprove, onReject }, ref) {
  const action = ACTION[rule.action] ?? { signal: "neutral" as Signal, label: rule.action };
  const status = STATUS[rule.status] ?? { text: rule.status, cls: "text-fm-muted" };
  const cond = conditionText(rule);
  return (
    <li
      ref={ref}
      onMouseEnter={() => onHover(rule.source_clause)}
      onMouseLeave={() => onHover(null)}
      className={cn("border-b border-fm-border px-3 py-2.5 transition-colors duration-[var(--fm-motion)] last:border-0", active && "bg-fm-hold-bg")}
    >
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="font-mono text-[12px] font-medium">{rule.rule_id ?? `rule-${rule.id}`}</span>
        <Tag tone="hold">§{rule.source_clause}</Tag>
        {rule.goods_category && <Tag>{rule.goods_category}</Tag>}
        <span className={cn("fm-label ml-auto !text-[10.5px]", status.cls)}>{status.text}</span>
      </div>

      <div className="mt-1.5 flex flex-wrap items-center gap-2">
        <code className={cn("rounded-fm-sm border border-fm-border bg-fm-sunken px-1.5 py-0.5 font-mono text-[12px]", !cond && "italic text-fm-faint")}>
          {cond ?? "no executable condition"}
        </code>
        <span className="text-fm-faint" aria-hidden>→</span>
        <StatusBadge signal={action.signal} label={action.label} size="sm" />
        {rule.signoff_role && (
          <span className="text-[11.5px] text-fm-muted">
            sign-off <span className="font-mono text-fm-text">{rule.signoff_role}</span>
          </span>
        )}
      </div>

      {rule.ambiguity && (
        <div className="mt-2 flex gap-2 rounded-fm-sm border border-fm-hold-line bg-fm-hold-bg px-2 py-1.5 text-[12px] leading-snug text-fm-text">
          <AlertTriangle size={13} className="mt-px shrink-0 text-fm-hold" aria-hidden />
          <span><span className="font-semibold text-fm-hold">Ambiguity.</span> {rule.ambiguity}</span>
        </div>
      )}

      {rule.status === "pending_approval" && (
        <div className="mt-2 flex gap-1.5">
          <Button size="xs" variant="verified" disabled={busy} onClick={() => onApprove(rule.id)}><Check size={12} aria-hidden />Approve</Button>
          <Button size="xs" variant="danger" disabled={busy} onClick={() => onReject(rule.id)}><X size={12} aria-hidden />Reject</Button>
        </div>
      )}
    </li>
  );
});
