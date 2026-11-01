"""Cases API: PO vs GRN vs invoice vs SAM, decided live with cited clauses.

No SQL, no verdict logic here -- CaseService owns both.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_case_service
from app.domain.schemas.cases import CaseDetail, CaseSummary
from app.services.cases import CaseService

router = APIRouter(tags=["cases"])


@router.get("/cases", response_model=list[CaseSummary])
def list_cases(
    service: CaseService = Depends(get_case_service),
) -> list[CaseSummary]:
    return service.list_cases()


@router.get("/cases/{po_id}", response_model=CaseDetail)
def get_case(
    po_id: int,
    service: CaseService = Depends(get_case_service),
) -> CaseDetail:
    return service.get_case(po_id)
