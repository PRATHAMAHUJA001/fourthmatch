"""Policy compiler service + API. Fake model client -- no live model calls."""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.api.deps import get_policy_service  # noqa: E402
from app.core.errors import ConflictError, NotFoundError  # noqa: E402
from app.domain.schemas.policies import ClauseClassification, CompileClauseOutput, ConflictReport  # noqa: E402
from app.infra.db.repositories.policies import SqlRuleRepository  # noqa: E402
from app.infra.db.session import Base, make_engine, make_session_factory  # noqa: E402
from app.main import create_app  # noqa: E402
from app.services.policy_compiler import PolicyCompilerService, split_clauses  # noqa: E402

POLICY_MD = """# Test Policy

**Version 9.9**

**1.1** Purchase Order means an approved order.

**4.2** Quantity tolerance is 0.0% for cartons; beyond it hold payment.

**4.3** Quantity within tolerance for cartons may be approved.

**4.9** Weight in kilograms must be checked at the dock.

**6.1** Damaged units are not payable; pay only the undamaged portion.
"""

_COMPILE: dict[str, dict[str, Any] | None] = {
    "1.1": None,
    "4.2": {
        "rule_id": "R-QTY-HOLD",
        "goods_category": "cartons",
        "condition": {"field": "variance_pct", "op": ">", "value": 0.0},
        "action": "hold",
        "signoff_role": None,
        "source_clause": "4.2",
        "source_text": "Quantity tolerance is 0.0% for cartons",
        "ambiguity": None,
    },
    "4.3": {
        "rule_id": "R-QTY-OK",
        "goods_category": "cartons",
        "condition": {"field": "variance_pct", "op": "<=", "value": 0.0},
        "action": "approve",
        "signoff_role": None,
        "source_clause": "4.3",
        "source_text": "Quantity within tolerance may be approved",
        "ambiguity": None,
    },
    "4.9": {
        "rule_id": "R-WEIGHT",
        "goods_category": "cartons",
        "condition": {"field": "weight_kg", "op": ">", "value": 1.0},
        "action": "hold",
        "signoff_role": None,
        "source_clause": "4.9",
        "source_text": "Weight must be checked",
        "ambiguity": "needs weight_kg, not in field list",
    },
    "6.1": {
        "rule_id": "R-DAMAGE",
        "goods_category": "all",
        "condition": {"field": "damage_count", "op": ">", "value": 0.0},
        "action": "partial_pay",
        "signoff_role": None,
        "source_clause": "6.1",
        "source_text": "Damaged units are not payable",
        "ambiguity": None,
    },
}

_CONFLICTS = {
    "conflicts": [
        {"rule_id_a": "R-QTY-HOLD", "rule_id_b": "R-QTY-OK", "reason": "same field, hold vs approve"},
        {"rule_id_a": "R-QTY-HOLD", "rule_id_b": "R-GHOST", "reason": "cites a rule that does not exist"},
        {"rule_id_a": "R-QTY-HOLD", "rule_id_b": "R-DAMAGE", "reason": "different fields -- must be dropped"},
    ]
}


class FakeModelClient:
    """Stands in for MetaModelClient; records prompts, returns canned JSON."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.retry_by_clause: dict[str, dict[str, Any]] = {}  # clause_id -> corrected rule

    async def call_model(self, *, purpose: str, prompt: str, output_schema: Any, **kwargs: Any) -> Any:
        self.calls.append({"purpose": purpose, "prompt": prompt, **kwargs})
        if purpose == "policy_conflicts":
            return ConflictReport.model_validate(_CONFLICTS)
        clause_id = prompt.split(":", 1)[0].replace("Clause", "").strip()
        if purpose == "policy_classify":
            kind = "definition" if clause_id == "1.1" else "payment_rule"
            return ClauseClassification.model_validate({"kind": kind})
        if purpose == "policy_compile_retry":
            fixed = self.retry_by_clause.get(clause_id)
            rule = fixed if fixed is not None else _COMPILE[clause_id]
            return CompileClauseOutput.model_validate({"rules": [] if rule is None else [rule]})
        rule = _COMPILE[clause_id]
        return CompileClauseOutput.model_validate({"rules": [] if rule is None else [rule]})


def _service(tmp_path: Path) -> tuple[PolicyCompilerService, FakeModelClient]:
    engine = make_engine(tmp_path / "rules.db")
    Base.metadata.create_all(engine)
    session = make_session_factory(engine)()
    fake = FakeModelClient()
    service = PolicyCompilerService(SqlRuleRepository(session), fake, "cfg-compiler")  # type: ignore[arg-type]
    return service, fake


def test_split_clauses() -> None:
    clauses = split_clauses(POLICY_MD)
    assert [c.clause_id for c in clauses] == ["1.1", "4.2", "4.3", "4.9", "6.1"]
    assert clauses[1].text.startswith("Quantity tolerance")


def test_split_real_policy_file() -> None:
    markdown = (ROOT / "data" / "policy" / "receiving_policy.md").read_text()
    clauses = split_clauses(markdown)
    ids = [c.clause_id for c in clauses]
    assert ids[0] == "1.1" and ids[-1] == "9.4"
    assert len(ids) == len(set(ids)) >= 30


def test_compile_policy_end_to_end(tmp_path: Path) -> None:
    service, fake = _service(tmp_path)
    result = asyncio.run(service.compile_policy(POLICY_MD))
    assert result.policy_version == "9.9"
    assert result.clauses_seen == 5
    assert result.skipped_non_rule == 1  # 1.1 is a definition
    assert result.rules_created == 4
    assert result.invalid == 1  # weight_kg not in catalog
    assert result.ambiguous == 1
    by_id = {r.rule_id: r for r in result.rules}
    assert by_id["R-WEIGHT"].validation_errors  # stored, never valid
    # Only the grounded conflict survives: ghost ID and different-field pair dropped.
    assert [(c.rule_id_a, c.rule_id_b) for c in result.conflicts] == [("R-QTY-HOLD", "R-QTY-OK")]
    assert by_id["R-QTY-HOLD"].conflict_with == ["R-QTY-OK"]
    assert all(r.status == "pending_approval" for r in result.rules)
    compile_calls = [c for c in fake.calls if c["purpose"] == "policy_compile"]
    assert len(compile_calls) == 4  # step 2 runs only for payment_rule clauses
    assert len([c for c in fake.calls if c["purpose"] == "policy_classify"]) == 5
    assert all(c["reasoning_effort"] == "high" for c in fake.calls)


_RETRY_FIXED_49 = {
    "rule_id": "R-QTY-CHECK",
    "goods_category": "cartons",
    "condition": {"field": "variance_pct", "op": ">", "value": 5.0},
    "action": "hold",
    "signoff_role": None,
    "source_clause": "4.9",
    "source_text": "quantity tolerance must be checked at the dock",
    "ambiguity": None,
}


def test_invalid_rule_retried_once_with_errors_and_corrected(tmp_path: Path) -> None:
    service, fake = _service(tmp_path)
    fake.retry_by_clause["4.9"] = _RETRY_FIXED_49
    result = asyncio.run(service.compile_policy(POLICY_MD))
    assert result.retries == 1  # only clause 4.9 failed validation
    assert result.invalid == 0  # the corrected rule validates
    by_id = {r.rule_id: r for r in result.rules}
    assert by_id["R-QTY-CHECK"].validation_errors == []
    retry_calls = [c for c in fake.calls if c["purpose"] == "policy_compile_retry"]
    assert len(retry_calls) == 1
    # The validator's errors and the rejected rule went back to the model.
    assert "weight_kg" in retry_calls[0]["prompt"]
    assert "unknown field" in retry_calls[0]["prompt"]
    first_calls = [c for c in fake.calls if c["purpose"] == "policy_compile"]
    assert len(first_calls) == 4  # both attempts exist in the call log


def test_retry_still_invalid_is_not_retried_again(tmp_path: Path) -> None:
    service, fake = _service(tmp_path)  # default fake: retry returns the same invalid rule
    result = asyncio.run(service.compile_policy(POLICY_MD))
    assert result.retries == 1
    assert result.invalid == 1
    assert len([c for c in fake.calls if c["purpose"] == "policy_compile_retry"]) == 1
    by_id = {r.rule_id: r for r in result.rules}
    assert by_id["R-WEIGHT"].validation_errors


def test_approve_reject_transitions(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    result = asyncio.run(service.compile_policy(POLICY_MD))
    target = next(r for r in result.rules if r.rule_id == "R-QTY-HOLD")
    approved = service.approve_rule(target.id)
    assert approved.status == "approved"
    with pytest.raises(ConflictError):
        service.approve_rule(target.id)
    other = next(r for r in result.rules if r.rule_id == "R-DAMAGE")
    assert service.reject_rule(other.id).status == "rejected"
    with pytest.raises(NotFoundError):
        service.approve_rule(99999)
    assert [r.rule_id for r in service.list_rules(status="approved")] == ["R-QTY-HOLD"]


@pytest.fixture()
def api_client(tmp_path: Path) -> Iterator[TestClient]:
    service, _ = _service(tmp_path)
    app = create_app()
    app.dependency_overrides[get_policy_service] = lambda: service
    with TestClient(app) as client:
        yield client


def test_api_compile_list_approve_reject(api_client: TestClient) -> None:
    resp = api_client.post(
        "/api/policies",
        files={"policy": ("policy.md", POLICY_MD.encode(), "text/markdown")},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["rules_created"] == 4 and body["clauses_seen"] == 5

    listed = api_client.get("/api/rules")
    assert listed.status_code == 200
    assert len(listed.json()) == 4

    rule_id = next(r["id"] for r in listed.json() if r["rule_id"] == "R-QTY-HOLD")
    approved = api_client.post(f"/api/rules/{rule_id}/approve")
    assert approved.status_code == 200 and approved.json()["status"] == "approved"
    assert api_client.post(f"/api/rules/{rule_id}/approve").status_code == 409

    other_id = next(r["id"] for r in listed.json() if r["rule_id"] == "R-DAMAGE")
    rejected = api_client.post(f"/api/rules/{other_id}/reject")
    assert rejected.status_code == 200 and rejected.json()["status"] == "rejected"

    pending = api_client.get("/api/rules", params={"status": "pending_approval"})
    assert {r["rule_id"] for r in pending.json()} == {"R-QTY-OK", "R-WEIGHT"}
    assert api_client.post("/api/rules/99999/approve").status_code == 404


def test_api_rejects_non_markdown(api_client: TestClient) -> None:
    resp = api_client.post(
        "/api/policies",
        files={"policy": ("policy.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "policy_not_markdown"
