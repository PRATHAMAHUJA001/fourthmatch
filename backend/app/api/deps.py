"""FastAPI dependencies: session, settings, repositories, services."""
from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.infra.db.repositories.purchase_orders import SqlPurchaseOrderRepository
from app.infra.db.session import make_engine, make_session_factory
from app.infra.storage import LocalFileStore
from app.services.deliveries import DeliveryService
from app.services.perception import PerceptionPipeline
from app.services.purchase_orders import PurchaseOrderService


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
