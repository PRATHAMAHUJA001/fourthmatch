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
      className={cn("rounded-[14px] px-4 py-4 transition-colors duration-200", active ? "bg-fm-hold-bg" : "hover:bg-fm-raised/70")}
    >
      <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
        <span className="font-mono text-[13px] font-medium">{rule.rule_id ?? `rule-${rule.id}`}</span>
        <span className="text-[13px] font-semibold text-fm-muted">§{rule.source_clause}</span>
        {rule.goods_category && <Tag>{rule.goods_category.replaceAll("_", " ")}</Tag>}
        <span className={cn("ml-auto text-[12px] font-semibold", status.cls)}>{status.text}</span>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <code className={cn("rounded-[10px] bg-fm-raised px-2.5 py-1 font-mono text-[12.5px]", active && "bg-fm-panel", !cond && "italic text-fm-faint")}>
          {cond ?? "no executable condition"}
        </code>
        <span className="text-fm-faint" aria-hidden>→</span>
        <StatusBadge signal={action.signal} label={action.label} size="sm" />
        {rule.signoff_role && (
          <span className="text-[12px] text-fm-muted">
            Sign-off: <span className="text-fm-text">{rule.signoff_role.replaceAll("_", " ")}</span>
          </span>
        )}
      </div>

      {rule.ambiguity && (
        <div className="mt-3 flex gap-2 rounded-[12px] bg-fm-hold-bg px-3 py-2.5 text-[13px] leading-snug text-fm-text">
          <AlertTriangle size={14} className="mt-px shrink-0 text-fm-hold" aria-hidden />
          <span><span className="font-semibold text-fm-hold">Ambiguous. </span>{rule.ambiguity}</span>
        </div>
      )}

      {rule.status === "pending_approval" && (
        <div className="mt-3 flex gap-2">
          <Button size="sm" variant="verified" disabled={busy} onClick={() => onApprove(rule.id)}><Check size={13} aria-hidden />Approve</Button>
          <Button size="sm" variant="danger" disabled={busy} onClick={() => onReject(rule.id)}><X size={13} aria-hidden />Reject</Button>
        </div>
      )}
    </li>
  );
});
