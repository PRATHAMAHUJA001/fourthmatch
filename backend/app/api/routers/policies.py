"""Policies API: upload a .md policy to compile it; approve/reject rules.

No SQL, no model calls here -- the compiler service owns both.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile

from app.api.deps import get_policy_service, get_simulation_service
from app.api.deps_demo import require_demo_passcode
from app.api.deps_reporting import get_policy_docs
from app.core.errors import ValidationError
from app.domain.schemas.dashboard import PolicyRead
from app.domain.schemas.policies import PolicyCompileResult, RuleRead
from app.domain.schemas.simulation import PolicySimulationResult, SimulatePolicyRequest
from app.services.policy_compiler import PolicyCompilerService, policy_version_of
from app.services.policy_docs import PolicyDocService
from app.services.simulation import PolicySimulationService

router = APIRouter(tags=["policies"])


@router.post("/policies", response_model=PolicyCompileResult, status_code=201, dependencies=[Depends(require_demo_passcode)])
async def upload_policy(
    policy: UploadFile = File(...),
    policy_version: str | None = Form(default=None),
    service: PolicyCompilerService = Depends(get_policy_service),
    policy_docs: PolicyDocService = Depends(get_policy_docs),
) -> PolicyCompileResult:
    filename = policy.filename or ""
    if not filename.lower().endswith(".md"):
        raise ValidationError("Policy upload must be a .md file.", code="policy_not_markdown")
    raw = await policy.read()
    if not raw.strip():
        raise ValidationError("Policy upload is empty.", code="policy_empty")
    try:
        markdown = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError("Policy upload must be UTF-8 text.", code="policy_not_utf8") from exc
    result = await service.compile_policy(markdown, policy_version=policy_version)
    # Keep the uploaded text: GET /policies/current serves the newest upload.
    policy_docs.save_uploaded(markdown, policy_version or policy_version_of(markdown))
    return result


@router.get("/policies/current", response_model=PolicyRead)
def current_policy(policy_docs: PolicyDocService = Depends(get_policy_docs)) -> PolicyRead:
    """The latest uploaded policy, or the bundled receiving policy when none was uploaded."""
    return policy_docs.current()


@router.post("/policies/{policy_id}/simulate", response_model=PolicySimulationResult, dependencies=[Depends(require_demo_passcode)])
async def simulate_policy(
    policy_id: str,
    request: SimulatePolicyRequest,
    service: PolicySimulationService = Depends(get_simulation_service),
) -> PolicySimulationResult:
    """Compile edited text to an in-memory draft and re-decide all past POs.

    {policy_id} is a policy_version. Read-only: no rule, decision, or draft
    is persisted. See services/simulation.py and domain/decision.py.
    """
    return await service.simulate(
        policy_version=policy_id, markdown=request.policy_text, draft_version=request.policy_version
    )


@router.get("/rules", response_model=list[RuleRead])
def list_rules(
    status: str | None = Query(default=None),
    service: PolicyCompilerService = Depends(get_policy_service),
) -> list[RuleRead]:
    return service.list_rules(status=status)


@router.post("/rules/{rule_id}/approve", response_model=RuleRead, dependencies=[Depends(require_demo_passcode)])
def approve_rule(
    rule_id: int,
    service: PolicyCompilerService = Depends(get_policy_service),
) -> RuleRead:
    return service.approve_rule(rule_id)


@router.post("/rules/{rule_id}/reject", response_model=RuleRead, dependencies=[Depends(require_demo_passcode)])
def reject_rule(
    rule_id: int,
    service: PolicyCompilerService = Depends(get_policy_service),
) -> RuleRead:
    return service.reject_rule(rule_id)
