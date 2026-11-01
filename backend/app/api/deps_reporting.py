"""FastAPI dependencies for the dashboard, policy-document and evidence endpoints.

Kept beside (not inside) api/deps.py so these wiring changes never collide
with other work on that module. Same pattern: session -> repository -> service.
"""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings, get_case_service, get_db_session
from app.core.config import REPO_ROOT, Settings
from app.domain.schemas.evidence import PackModels
from app.infra.db.repositories.dashboard import SqlDashboardRepository
from app.infra.db.repositories.evidence import SqlEvidenceRepository
from app.infra.frames import VideoFrameSource
from app.infra.pdf import ReportLabRenderer
from app.infra.storage import LocalFileStore
from app.services.cases import CaseService
from app.services.dashboard import DashboardService
from app.services.evidence import EvidenceService
from app.services.policy_docs import PolicyDocService

DATA_DIR = REPO_ROOT / "data"
DEFAULT_POLICY_PATH = DATA_DIR / "policy" / "receiving_policy.md"


def get_policy_docs(settings: Settings = Depends(get_app_settings)) -> PolicyDocService:
    return PolicyDocService(LocalFileStore(settings.storage_root), DEFAULT_POLICY_PATH)


def get_dashboard_service(
    session: Session = Depends(get_db_session),
    cases: CaseService = Depends(get_case_service),
) -> DashboardService:
    return DashboardService(
        cases,
        SqlDashboardRepository(session),
        ground_truth_path=DATA_DIR / "ground_truth.json",
        eval_counts_path=DATA_DIR / "eval_counts.json",
        eval_results_path=DATA_DIR / "eval_results.json",
    )


def get_evidence_service(
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_app_settings),
    cases: CaseService = Depends(get_case_service),
    policy_docs: PolicyDocService = Depends(get_policy_docs),
) -> EvidenceService:
    models = PackModels(
        perception_model=settings.perception_model,
        decision_model=settings.decision_model,
        compiler_model=settings.compiler_model,
        seg_model=settings.seg_model,
    )
    return EvidenceService(
        cases,
        SqlEvidenceRepository(session),
        LocalFileStore(settings.storage_root),
        ReportLabRenderer(),
        VideoFrameSource(settings.storage_root, REPO_ROOT, settings.sam_proxy_fps),
        models,
        policy_provider=policy_docs.current,
    )
