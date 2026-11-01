"""FastAPI dependencies: session, settings, repositories, services."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import UpstreamModelError
from app.infra.cache import Sha256Cache
from app.infra.db.repositories.cases import SqlCaseRepository
from app.infra.db.repositories.policies import SqlRuleRepository
from app.infra.db.repositories.purchase_orders import SqlPurchaseOrderRepository
from app.infra.db.repositories.simulation import SqlSimulationRepository
from app.infra.db.session import make_engine, make_session_factory
from app.infra.meta.client import MetaModelClient
from app.infra.storage import LocalFileStore
from app.services.cases import CaseService
from app.services.decision_agent import DecisionAgent
from app.services.deliveries import DeliveryService
from app.services.perception import PerceptionPipeline
from app.services.policy_compiler import PolicyCompilerService
from app.services.purchase_orders import PurchaseOrderService
from app.services.simulation import PolicySimulationService


def get_db_session() -> Iterator[Session]:
    factory = make_session_factory(make_engine())
    session = factory()
    try:
        yield session
    finally:
        session.close()


def get_app_settings() -> Settings:
    return get_settings()


def get_po_service(session: Session = Depends(get_db_session)) -> PurchaseOrderService:
    return PurchaseOrderService(SqlPurchaseOrderRepository(session))


def get_case_service(session: Session = Depends(get_db_session)) -> CaseService:
    return CaseService(SqlCaseRepository(session))


def get_delivery_service(settings: Settings = Depends(get_app_settings)) -> DeliveryService:
    factory = make_session_factory(make_engine())
    return DeliveryService(factory, LocalFileStore(settings.storage_root))


def get_pipeline_runner(settings: Settings = Depends(get_app_settings)):  # noqa: ANN202
    """Callable(job_id, delivery_id) run as a FastAPI background task."""
    factory = make_session_factory(make_engine())
    pipeline = PerceptionPipeline(settings, factory)

    async def _run(job_id: str, delivery_id: int) -> dict:
        return await pipeline.run(job_id, delivery_id)

    return _run


def get_policy_service(
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_app_settings),
) -> PolicyCompilerService:
    config = settings.model_config_model()
    cache = Sha256Cache(settings.cache_root)
    client = MetaModelClient(config, cache=cache)
    return PolicyCompilerService(
        SqlRuleRepository(session), client, settings.compiler_model, session=session, cache=cache
    )


def get_simulation_service(
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_app_settings),
) -> PolicySimulationService:
    config = settings.model_config_model()
    cache = Sha256Cache(settings.cache_root)
    client = MetaModelClient(config, cache=cache)
    compiler = PolicyCompilerService(
        SqlRuleRepository(session), client, settings.compiler_model, session=session, cache=cache
    )
    return PolicySimulationService(SqlSimulationRepository(session), compiler)


def get_decision_agent(settings: Settings = Depends(get_app_settings)) -> DecisionAgent:
    try:
        config = settings.model_config_model()
    except ValueError as exc:
        raise UpstreamModelError(str(exc), code="model_not_configured") from exc
    factory = make_session_factory(make_engine())
    client = MetaModelClient(config, cache=Sha256Cache(settings.cache_root))
    return DecisionAgent(factory, client, config.decision_model, max_turns=settings.max_agent_turns)
