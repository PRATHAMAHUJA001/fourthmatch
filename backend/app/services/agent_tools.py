"""Deterministic tools the payment-decision agent may call.

Each tool is pure Python over a CaseFacts snapshot: no model, no I/O, no
arithmetic of its own (variance, value at risk and rule outcomes all come
from domain.decision / domain.rules via domain.agent_logic). A call that
cites an unknown ID returns {"error": ...} and is NOT counted as coverage.
"""

from __future__ import annotations

from typing import Any

from app.domain import agent_logic
from app.domain.schemas.decision_agent import CaseFacts, ToolCoverage

RECORD_DECISION = "record_decision"

_EVIDENCE_NOTE = (
    "Cite evidence as strings: 'track:<track_id>' and 'frame:<frame_index>' "
    "using only the track_ids and frame range given by get_case."
)


def tool_definitions() -> list[dict[str, Any]]:
    """Flat tool definitions (MODEL_NOTES §3); tool_choice is left at auto."""

    def fn(name: str, description: str, properties: dict[str, Any], required: list[str],
           strict: bool = True) -> dict[str, Any]:
        return {
            "type": "function", "name": name, "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required,
                           "additionalProperties": False},
            "strict": strict,
        }

    return [
        fn("get_case", "Get the PO, GRN, invoice and video perception result for a delivery. " + _EVIDENCE_NOTE,
           {"delivery_id": {"type": "integer"}}, ["delivery_id"]),
        fn("compute_variance",
           "Python-computed po, grn, invoiced, observed, variance_pct and value_at_risk_paise for one PO line.",
           {"po_line_id": {"type": "integer"}}, ["po_line_id"]),
        fn("get_rules", "List the approved policy rules (rule_id, clause, action, condition) for a goods category.",
           {"goods_category": {"type": "string"}}, ["goods_category"]),
        fn("evaluate_rule", "Evaluate one approved rule against one PO line. Returns fired and why.",
           {"rule_id": {"type": "string"}, "po_line_id": {"type": "integer"}}, ["rule_id", "po_line_id"]),
        fn("draft_debit_note",
           "Draft a debit note for the disputed portion of the given PO lines. Amounts are computed in Python.",
           {"invoice_id": {"type": "integer"},
            "lines": {"type": "array", "items": {
                "type": "object",
                "properties": {"po_line_id": {"type": "integer"}, "reason": {"type": "string"}},
                "required": ["po_line_id", "reason"], "additionalProperties": False}}},
           ["invoice_id", "lines"]),
        fn(RECORD_DECISION,
           "Final call. Record the decision. amount_held_paise is an integer in paise copied from tool outputs. "
           + _EVIDENCE_NOTE,
           {"verdict": {"type": "string", "enum": ["approve", "partial_pay", "hold", "human_review"]},
            "amount_held_paise": {"type": "integer"},
            "lines": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "po_line_id": {"type": "integer"}, "po": {"type": "integer"},
                    "grn": {"type": ["integer", "null"]}, "invoiced": {"type": "integer"},
                    "observed": {"type": ["integer", "null"]},
                    "variance_pct": {"type": ["number", "null"]},
                    "rule_id": {"type": ["string", "null"]}, "clause": {"type": ["string", "null"]},
                    "evidence": {"type": "array", "items": {"type": "string"}}},
                "required": ["po_line_id", "po", "grn", "invoiced", "observed", "variance_pct",
                             "rule_id", "clause", "evidence"],
                "additionalProperties": False}},
            "summary_en": {"type": "string"}, "recommended_action": {"type": "string"}},
           ["verdict", "amount_held_paise", "lines", "summary_en", "recommended_action"], strict=False),
    ]


class CaseToolbox:
    """Executes the non-final tools and records which calls truly succeeded."""

    def __init__(self, facts: CaseFacts) -> None:
        self._facts = facts
        self.coverage = ToolCoverage()
        self._lines = {ln.po_line_id: ln for ln in facts.lines}
        self._rules = {r.rule_id: r for r in facts.rules}

    def execute(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        handler = {
            "get_case": self._get_case,
            "compute_variance": self._compute_variance,
            "get_rules": self._get_rules,
            "evaluate_rule": self._evaluate_rule,
            "draft_debit_note": self._draft_debit_note,
        }.get(name)
        if handler is None:
            return {"error": f"unknown tool {name!r}"}
        try:
            return handler(args)
        except (KeyError, TypeError, ValueError) as exc:
            return {"error": f"bad arguments for {name}: {exc}"}

    # -- tools -------------------------------------------------------------

    def _get_case(self, args: dict[str, Any]) -> dict[str, Any]:
        delivery_id = int(args["delivery_id"])
        if delivery_id != self._facts.delivery_id:
            return {"error": f"unknown delivery_id {delivery_id}"}
        f = self._facts
        lines: list[dict[str, Any]] = []
        for ln in f.lines:
            inp = ln.facts
            lines.append({
                "po_line_id": ln.po_line_id, "line_no": ln.line_no, "sku": ln.sku,
                "description": ln.description, "category": ln.category, "unit": ln.unit,
                "has_evidence": inp is not None,
                "po_qty": inp.po_qty if inp else None,
                "grn_qty": inp.grn_qty if inp else None,
                "invoiced_qty": inp.invoiced_qty if inp else None,
                "unit_price_paise": inp.unit_price_paise if inp else None,
                "po_unit_price_paise": inp.po_unit_price_paise if inp else None,
                "evidence_source": inp.evidence_source if inp else "none",
                "evidence_quality": inp.evidence_quality if inp else None,
                "duplicate_invoice": inp.duplicate_invoice if inp else False,
                "perception": ln.perception.model_dump() if ln.perception else None,
                "tracks": [t.model_dump() for t in ln.tracks],
            })
        return {
            "delivery_id": f.delivery_id, "po_number": f.po_number, "vendor": f.vendor_name,
            "grn_number": f.grn_number, "invoice_id": f.invoice_id,
            "invoice_number": f.invoice_number, "invoice_total_paise": f.invoice_total_paise,
            "policy_version": f.policy_version, "lines": lines,
        }

    def _line(self, args: dict[str, Any]) -> Any:
        po_line_id = int(args["po_line_id"])
        line = self._lines.get(po_line_id)
        if line is None:
            raise ValueError(f"unknown po_line_id {po_line_id}")
        if line.facts is None:
            raise ValueError(f"po_line_id {po_line_id} has no observed evidence (no video, no GRN)")
        return line

    def _compute_variance(self, args: dict[str, Any]) -> dict[str, Any]:
        line = self._line(args)
        result = agent_logic.variance_result(line)
        self.coverage.variance_lines.add(line.po_line_id)
        return result.model_dump()

    def _get_rules(self, args: dict[str, Any]) -> dict[str, Any]:
        category = str(args["goods_category"])
        rules = agent_logic.rules_for_category(self._facts.rules, category)
        return {"goods_category": category, "rules": [
            {"rule_id": r.rule_id, "clause": r.source_clause, "action": r.action,
             "signoff_role": r.signoff_role, "goods_category": r.goods_category or "all",
             "condition": r.condition.model_dump(), "source_text": r.source_text}
            for r in rules]}

    def _evaluate_rule(self, args: dict[str, Any]) -> dict[str, Any]:
        rule_id = str(args["rule_id"])
        rule = self._rules.get(rule_id)
        if rule is None:
            raise ValueError(f"unknown rule_id {rule_id!r}")
        line = self._line(args)
        result = agent_logic.evaluate_rule_for_line(rule, line)
        self.coverage.evaluated.add((rule_id, line.po_line_id))
        return result.model_dump()

    def _draft_debit_note(self, args: dict[str, Any]) -> dict[str, Any]:
        items = [(int(item["po_line_id"]), str(item["reason"])) for item in args["lines"]]
        draft = agent_logic.draft_debit_note(self._facts, int(args["invoice_id"]), items)
        return draft.model_dump()
