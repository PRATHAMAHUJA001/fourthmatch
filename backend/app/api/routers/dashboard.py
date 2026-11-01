"""Dashboard API: Dock KPIs, analytics, eval. Read-only; no SQL or math here."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps_reporting import get_dashboard_service
from app.domain.schemas.dashboard import AnalyticsRead, DockKpis, EvalRead
from app.services.dashboard import DashboardService

router = APIRouter(tags=["dashboard"])


@router.get("/dock/kpis", response_model=DockKpis)
def dock_kpis(service: DashboardService = Depends(get_dashboard_service)) -> DockKpis:
    return service.dock_kpis()


@router.get("/analytics", response_model=AnalyticsRead)
def analytics(service: DashboardService = Depends(get_dashboard_service)) -> AnalyticsRead:
    return service.analytics()


@router.get("/eval", response_model=EvalRead)
def evaluation(service: DashboardService = Depends(get_dashboard_service)) -> EvalRead:
    return service.evaluation()
