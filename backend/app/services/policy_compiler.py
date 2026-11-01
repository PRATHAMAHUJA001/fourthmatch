"""Policy compiler: split a .md policy into clauses, compile each clause
with COMPILER_MODEL into a rule, validate in Python, detect conflicts with
one more model call, and persist everything as PENDING_APPROVAL.

All model output is validated against Pydantic schemas by the client, then
against the field catalog in domain/rules.py. Every rule_id the conflict
call cites is checked in Python to exist and to actually share
category+field before it is stored.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.core.logging import get_logger
from app.domain.enums import RuleStatus
from app.domain.protocols import RuleRepository
from app.domain.rules import _norm_category, strict_validate_rule
from app.domain.schemas.policies import (
    ApproverRoute,
    Clause,
    ClauseClassification,
    CompileClauseOutput,
    CompiledRule,
    ConflictPair,
    ConflictReport,
    PolicyCompileResult,
    RuleCondition,
    RuleRead,
)
from app.domain.schemas.simulation import DraftCompileResult, DraftRule
from app.infra.cache import Sha256Cache, cache_key_for, sha256_hex
from app.infra.meta.client import MetaModelClient

logger = get_logger(__name__)

COMPILER_PROMPT_VERSION = "policy-compiler-v3"
CLASSIFY_SYSTEM_PROMPT = (
    "Classify ONE procurement policy clause into exactly one kind. "
    "'payment_rule' = it states a checkable condition on a delivery/invoice that can "
    "hold, partially pay, or release payment. 'approval_authority' = it only states WHO "
    "may approve and up to what invoice value (a role plus a value band) -- extract role, "
    "min_value_inr and max_value_inr (rupees, null for an open end). 'procedural' = a "
    "process step, duty, document or record-keeping requirement with no payment condition. "
    "'definition' = it defines a term or states purpose/background. Return only JSON: "
    '{"kind":"payment_rule|approval_authority|procedural|definition","role":null,'
    '"min_value_inr":null,"max_value_inr":null}'
)
COMPILER_SYSTEM_PROMPT = (
    "Convert ONE procurement policy clause into executable payment rules. Use only these fields: "
    "observed_count, invoiced_qty, po_qty, grn_qty, damage_count, unit_price, line_value, "
    "goods_category, variance_pct, variance_vs_invoice_pct, price_variance_pct, "
    "invoiced_vs_po_pct, duplicate_invoice. Facts you may reference: variance_pct is "
    "(po_qty - observed)/po_qty*100; variance_vs_invoice_pct is (invoiced - observed)/invoiced*100; "
    "price_variance_pct is (invoice_price - po_price)/po_price*100; invoiced_vs_po_pct is "
    "(invoiced_qty - po_qty)/po_qty*100; duplicate_invoice is a boolean (another invoice with "
    "the same vendor and invoice number exists) -- for it use op '==' and value true. "
    "ONE threshold per rule: condition.value IS the tolerance -- put the full tolerance "
    "number in value (e.g. a 2% tolerance is value 2.0 with op '>'), never split it. "
    "If the clause gives per-category tolerances, return ONE rule per category: set "
    "goods_category to that category and value to that category's tolerance. "
    "The condition field must be a fact the clause text actually mentions -- never invent "
    "a condition (such as line_value > 0) that the clause does not state. "
    "Actions mean exactly this: 'hold' = withhold the ENTIRE line value (never use it when "
    "only part of the line is disputed); 'partial_pay' = pay for the received correct units "
    "and withhold only the disputed portion (use it for shortage, damage, invoiced-above-"
    "received and invoiced-above-PO clauses); 'require_signoff' = a human must approve before "
    "ANY payment (set signoff_role); 'approve' = pay in full. If the clause needs a field not "
    "in this list, set ambiguity on the rule to explain why and do not guess. Return only JSON: "
    '{"rules":[{"rule_id":"","goods_category":"","condition":{"field":"",'
    '"op":"<|<=|>|>=|==|between","value":null},'
    '"action":"approve|partial_pay|hold|require_signoff","signoff_role":null,'
    '"source_clause":"4.2","source_text":"<verbatim clause>","ambiguity":null}]}'
)

RETRY_SYSTEM_PROMPT = (
    "Your previous conversion of this clause into payment rules was rejected by "
    "Python validation. Correct it: fix every validation error listed below, keep "
    "the meaning of any rule that was already valid, and return the complete "
    "corrected rule set for the same clause in exactly the same JSON shape, "
    "following all of the original conversion instructions above."
)

CONFLICT_PROMPT_VERSION = "policy-conflicts-v1"
CONFLICT_SYSTEM_PROMPT = (
    "You compare compiled procurement rules. Two rules conflict or overlap when they share "
    "the same goods_category and the same condition field but prescribe contradicting or "
    "overlapping actions for overlapping condition ranges. Use only the rule_ids given. "
    "Return only JSON: "
    '{"conflicts":[{"rule_id_a":"","rule_id_b":"","reason":""}]}'
)

_CLAUSE_RE = re.compile(r"\*\*(\d+\.\d+)\*\*\s*")
_VERSION_RE = re.compile(r"\*\*Version\s+([0-9][0-9A-Za-z.\-]*)\*\*", re.IGNORECASE)


def split_clauses(markdown: str) -> list[Clause]:
    """Split policy markdown on **N.N** clause markers. Pure and tested."""
    matches = list(_CLAUSE_RE.finditer(markdown))
    clauses: list[Clause] = []
    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
        text = markdown[start:end].strip()
        # Drop trailing section headings / horizontal rules from the last chunk.
        text = re.split(r"\n#{1,6}\s", text, maxsplit=1)[0].strip()
        if text:
            clauses.append(Clause(clause_id=match.group(1), text=text))
    return clauses


def policy_version_of(markdown: str) -> str:
    match = _VERSION_RE.search(markdown)
    return match.group(1) if match else "unknown"


def clause_rule_errors(clause: Clause, rules: list[CompiledRule]) -> list[list[str]]:
    """Per-rule strict validation errors for one clause's compiled rules."""
    out: list[list[str]] = []
    for rule in rules:
        errors = strict_validate_rule(rule)
        if rule.source_clause != clause.clause_id:
            errors.append(
                f"source_clause mismatch: model cited {rule.source_clause!r}, clause is {clause.clause_id!r}"
            )
        out.append(errors)
    return out


def retry_cache_key(model: str, clause: Clause, rules: list[CompiledRule],
                    errors: list[str]) -> str:
    """Cache key for the one validator-feedback retry of a clause.

    Keyed on the clause text plus the rejected rules and their sorted errors,
    so a retry is never served the first attempt's cached (invalid) output,
    and offline scorers can reconstruct the key from the cached first attempt.
    """
    payload = json.dumps(
        {"rules": [r.model_dump() for r in rules], "errors": sorted(errors)},
        sort_keys=True,
    )
    return cache_key_for(
        "policy_compile_retry", COMPILER_PROMPT_VERSION, model,
        sha256_hex(clause.text.encode()), sha256_hex(payload.encode()),
    )


def _rule_read(row: object) -> RuleRead:
    condition = None
    if getattr(row, "condition_field", None):
        condition = RuleCondition(
            field=row.condition_field,  # type: ignore[attr-defined]
            op=row.condition_op or "",  # type: ignore[attr-defined]
            value=row.condition_value,  # type: ignore[attr-defined]
        )
    return RuleRead(
        id=row.id,  # type: ignore[attr-defined]
        rule_id=row.rule_id,  # type: ignore[attr-defined]
        goods_category=row.goods_category or row.category,  # type: ignore[attr-defined]
        condition=condition,
        tolerance_pct=row.tolerance_pct if row.tolerance_pct is not None else row.threshold_pct,  # type: ignore[attr-defined]
        action=row.action,  # type: ignore[attr-defined]
        signoff_role=row.signoff_role,  # type: ignore[attr-defined]
        source_clause=row.clause,  # type: ignore[attr-defined]
        source_text=row.source_text,  # type: ignore[attr-defined]
        ambiguity=row.ambiguity,  # type: ignore[attr-defined]
        status=row.status or RuleStatus.PENDING_APPROVAL.value,  # type: ignore[attr-defined]
        validation_errors=list(row.validation_errors or []),  # type: ignore[attr-defined]
        conflict_with=list(row.conflict_with or []),  # type: ignore[attr-defined]
        policy_version=row.policy_version,  # type: ignore[attr-defined]
    )


@dataclass
class _ClauseCompile:
    clause: Clause
    rule: CompiledRule  # rule_id already de-duplicated
    errors: list[str] = field(default_factory=list)


@dataclass
class _CompileOutcome:
    items: list[_ClauseCompile]  # one entry per compiled rule (a clause may yield several)
    routes: list[ApproverRoute]
    skipped: int
    invalid: int
    ambiguous: int
    compiled: int  # model calls made (cache misses, both steps)
    cache_hits: int
    retries: int = 0  # clauses retried once after validation failure


_CLAUSE_KINDS = ("payment_rule", "approval_authority", "procedural", "definition")


class PolicyCompilerService:
    def __init__(
        self,
        repository: RuleRepository,
        model_client: MetaModelClient,
        compiler_model: str,
        *,
        session: Session | None = None,
        cache: Sha256Cache | None = None,
    ) -> None:
        self._repository = repository
        self._model = model_client
        self._compiler_model = compiler_model
        self._session = session
        self._cache = cache

    async def _call_step(self, purpose: str, clause: Clause, instructions: str,
                         output_schema: type, counters: dict[str, int], *,
                         prompt: str | None = None, cache_key: str | None = None):  # noqa: ANN202
        """One cached model step for one clause; counts compiled vs cache hit."""
        cache_key = cache_key or cache_key_for(
            purpose, COMPILER_PROMPT_VERSION, self._compiler_model,
            sha256_hex(clause.text.encode()),
        )
        if self._cache is not None and self._cache.get_json(cache_key) is not None:
            counters["cache_hits"] += 1
        else:
            counters["compiled"] += 1
        return await self._model.call_model(
            purpose=purpose,
            model=self._compiler_model,
            prompt=prompt or f"Clause {clause.clause_id}: {clause.text}",
            instructions=instructions,
            output_schema=output_schema,
            session=self._session,
            reasoning_effort="high",
            cache_key=cache_key,
        )

    async def _retry_compile(self, clause: Clause, rules: list[CompiledRule],
                             errors: list[str], counters: dict[str, int]) -> CompileClauseOutput:
        """One validator-feedback retry: original clause + rejected rules + errors."""
        counters["retries"] += 1
        prompt = (
            f"Clause {clause.clause_id}: {clause.text}\n"
            f"Previous rules JSON:\n{json.dumps([r.model_dump() for r in rules])}\n"
            "Validation errors:\n" + "\n".join(f"- {e}" for e in errors)
        )
        output: CompileClauseOutput = await self._call_step(
            "policy_compile_retry", clause,
            f"{COMPILER_SYSTEM_PROMPT}\n{RETRY_SYSTEM_PROMPT}",
            CompileClauseOutput, counters, prompt=prompt,
            cache_key=retry_cache_key(self._compiler_model, clause, rules, errors),
        )
        return output

    async def _compile_clauses(self, markdown: str) -> _CompileOutcome:
        """Two-step compile, in memory. No persistence, no conflict call.

        Step 1 classifies each clause; only payment_rule clauses reach
        step 2. approval_authority clauses become approver routes and never
        rules. Both steps are cached per clause hash (sha256 of clause text
        + model + COMPILER_PROMPT_VERSION), so an edited clause recompiles
        alone. Compiled rules face strict validation: catalog + tautology /
        unsatisfiability on boundary facts + field-mentioned-in-clause. A
        clause whose rules fail validation gets exactly one retry with the
        validator's errors fed back to the model (both attempts are model
        calls, both logged); a still-invalid retry result stays invalid.
        """
        items: list[_ClauseCompile] = []
        routes: list[ApproverRoute] = []
        seen_rule_ids: set[str] = set()
        skipped = invalid = ambiguous = 0
        counters = {"compiled": 0, "cache_hits": 0, "retries": 0}
        clauses = split_clauses(markdown)

        for clause in clauses:
            classification: ClauseClassification = await self._call_step(
                "policy_classify", clause, CLASSIFY_SYSTEM_PROMPT,
                ClauseClassification, counters,
            )
            kind = classification.kind if classification.kind in _CLAUSE_KINDS else "procedural"
            if kind == "approval_authority":
                role = (classification.role or "").strip()
                if role:
                    routes.append(ApproverRoute(
                        source_clause=clause.clause_id, role=role,
                        min_value_inr=classification.min_value_inr,
                        max_value_inr=classification.max_value_inr,
                    ))
                skipped += 1
                continue
            if kind != "payment_rule":
                skipped += 1
                continue

            output: CompileClauseOutput = await self._call_step(
                "policy_compile", clause, COMPILER_SYSTEM_PROMPT,
                CompileClauseOutput, counters,
            )
            if not output.rules:
                skipped += 1
                continue
            errors_by_rule = clause_rule_errors(clause, output.rules)
            if any(errors_by_rule):
                # Max 1 retry: send the validator's errors back with the
                # clause and the rejected rules; the retry replaces them.
                flat_errors = [e for errs in errors_by_rule for e in errs]
                retry_output = await self._retry_compile(
                    clause, output.rules, flat_errors, counters)
                if retry_output.rules:
                    output = retry_output
                    errors_by_rule = clause_rule_errors(clause, output.rules)
            for rule, errors in zip(output.rules, errors_by_rule, strict=True):
                if rule.ambiguity:
                    ambiguous += 1
                stored_rule_id = rule.rule_id.strip() or f"clause-{clause.clause_id}"
                if stored_rule_id in seen_rule_ids:
                    errors.append(f"duplicate rule_id: {stored_rule_id!r}")
                    stored_rule_id = f"{stored_rule_id}#{clause.clause_id}"
                seen_rule_ids.add(stored_rule_id)
                if errors:
                    invalid += 1
                items.append(_ClauseCompile(
                    clause=clause,
                    rule=rule.model_copy(update={"rule_id": stored_rule_id}),
                    errors=errors,
                ))
        return _CompileOutcome(
            items=items, routes=routes, skipped=skipped, invalid=invalid,
            ambiguous=ambiguous, compiled=counters["compiled"],
            cache_hits=counters["cache_hits"], retries=counters["retries"],
        )

    async def compile_draft(self, markdown: str, policy_version: str | None = None) -> DraftCompileResult:
        """Compile edited policy text into an in-memory draft rule set.

        Nothing is persisted and nothing is approved; invalid rules are
        returned with their validation errors and must never be evaluated.
        """
        outcome = await self._compile_clauses(markdown)
        return DraftCompileResult(
            policy_version=policy_version or policy_version_of(markdown),
            clauses_seen=len(split_clauses(markdown)),
            skipped_non_rule=outcome.skipped,
            invalid=outcome.invalid,
            ambiguous=outcome.ambiguous,
            compiled=outcome.compiled,
            cache_hits=outcome.cache_hits,
            retries=outcome.retries,
            approver_routes=outcome.routes,
            rules=[
                DraftRule(rule=item.rule, validation_errors=item.errors)
                for item in outcome.items
            ],
        )

    async def compile_policy(self, markdown: str, policy_version: str | None = None) -> PolicyCompileResult:
        version = policy_version or policy_version_of(markdown)
        outcome = await self._compile_clauses(markdown)
        created: list[RuleRead] = []
        valid_rules: list[CompiledRule] = []
        row_by_rule_id: dict[str, int] = {}

        for item in outcome.items:
            rule, clause = item.rule, item.clause
            errors = item.errors
            row = self._repository.create_rule(
                clause=clause.clause_id,
                policy_version=version,
                category=rule.goods_category or None,
                rule_type=f"compiled:{rule.condition.field}",
                threshold_pct=None,
                threshold_paise=None,
                action=rule.action,
                description=(
                    f"Compiled from clause {clause.clause_id}: "
                    f"{rule.condition.field} {rule.condition.op} {rule.condition.value}"
                ),
                rule_id=rule.rule_id,
                goods_category=rule.goods_category or None,
                condition_field=rule.condition.field,
                condition_op=rule.condition.op,
                condition_value=rule.condition.value,
                tolerance_pct=None,
                signoff_role=rule.signoff_role,
                source_text=rule.source_text,
                ambiguity=rule.ambiguity,
                status=RuleStatus.PENDING_APPROVAL.value,
                validation_errors=errors,
                conflict_with=[],
            )
            created.append(_rule_read(row))
            row_by_rule_id[rule.rule_id] = row.id
            if not errors:
                valid_rules.append(rule)

        conflicts = await self._detect_conflicts(valid_rules)
        conflicts_by_rule: dict[str, set[str]] = {}
        for pair in conflicts:
            conflicts_by_rule.setdefault(pair.rule_id_a, set()).add(pair.rule_id_b)
            conflicts_by_rule.setdefault(pair.rule_id_b, set()).add(pair.rule_id_a)
        for rule_id, others in conflicts_by_rule.items():
            pk = row_by_rule_id.get(rule_id)
            if pk is not None:
                self._repository.set_conflicts(pk, sorted(others))
        self._repository.commit()

        refreshed = [_rule_read(r) for r in self._repository.list_rules()]
        created_ids = {r.id for r in created}
        return PolicyCompileResult(
            policy_version=version,
            clauses_seen=len(split_clauses(markdown)),
            rules_created=len(created),
            skipped_non_rule=outcome.skipped,
            invalid=outcome.invalid,
            ambiguous=outcome.ambiguous,
            compiled=outcome.compiled,
            cache_hits=outcome.cache_hits,
            retries=outcome.retries,
            conflicts=conflicts,
            approver_routes=outcome.routes,
            rules=[r for r in refreshed if r.id in created_ids],
        )

    async def _detect_conflicts(self, rules: list[CompiledRule]) -> list[ConflictPair]:
        if len(rules) < 2:
            return []
        payload = json.dumps([r.model_dump() for r in rules])
        cache_key = cache_key_for(
            "policy_conflicts",
            CONFLICT_PROMPT_VERSION,
            self._compiler_model,
            sha256_hex(payload.encode()),
        )
        report: ConflictReport = await self._model.call_model(
            purpose="policy_conflicts",
            model=self._compiler_model,
            prompt=f"Rules:\n{payload}",
            instructions=CONFLICT_SYSTEM_PROMPT,
            output_schema=ConflictReport,
            session=self._session,
            reasoning_effort="high",
            cache_key=cache_key,
        )
        by_id = {r.rule_id: r for r in rules}
        kept: list[ConflictPair] = []
        seen: set[tuple[str, str]] = set()
        for pair in report.conflicts:
            a, b = by_id.get(pair.rule_id_a), by_id.get(pair.rule_id_b)
            if a is None or b is None or pair.rule_id_a == pair.rule_id_b:
                continue  # cited an ID Python cannot verify -> reject
            key = tuple(sorted((pair.rule_id_a, pair.rule_id_b)))
            if key in seen:
                continue
            # Ground the model's claim: same category + field, different action.
            if _norm_category(a.goods_category) != _norm_category(b.goods_category):
                continue
            if a.condition.field != b.condition.field or a.action == b.action:
                continue
            seen.add(key)  # type: ignore[arg-type]
            kept.append(pair)
        return kept

    def list_rules(self, status: str | None = None) -> list[RuleRead]:
        return [_rule_read(r) for r in self._repository.list_rules(status=status)]

    def approve_rule(self, rule_pk: int) -> RuleRead:
        return self._transition(rule_pk, RuleStatus.APPROVED)

    def reject_rule(self, rule_pk: int) -> RuleRead:
        return self._transition(rule_pk, RuleStatus.REJECTED)

    def _transition(self, rule_pk: int, target: RuleStatus) -> RuleRead:
        row = self._repository.get_rule(rule_pk)
        if row is None:
            raise NotFoundError(f"Rule {rule_pk} was not found.", code="rule_not_found")
        if row.status != RuleStatus.PENDING_APPROVAL.value:
            raise ConflictError(f"Rule {rule_pk} is already {row.status}.", code="rule_already_decided")
        updated = self._repository.set_status(rule_pk, target.value)
        self._repository.commit()
        assert updated is not None
        return _rule_read(updated)
