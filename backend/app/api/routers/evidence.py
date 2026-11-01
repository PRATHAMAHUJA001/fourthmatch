"""Evidence API: build/download evidence packs and debit notes, verify by hash.

No hashing, rendering or SQL here -- EvidenceService owns all of it.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from app.api.deps_reporting import get_evidence_service
from app.domain.schemas.dashboard import EvidenceVerifyRead
from app.domain.schemas.evidence import EvidenceFile, EvidencePackRead
from app.services.evidence import EvidenceService

router = APIRouter(tags=["evidence"])


def _file_response(file: EvidenceFile) -> Response:
    return Response(
        content=file.data,
        media_type=file.media_type,
        headers={"Content-Disposition": f'inline; filename="{file.name}"'},
    )


@router.get("/deliveries/{delivery_id}/evidence-pack")
def get_evidence_pack(
    delivery_id: int,
    format: Literal["pdf", "json"] = Query(default="pdf"),
    service: EvidenceService = Depends(get_evidence_service),
) -> Response:
    """The latest pack as PDF (default) or its exact JSON bytes; built on first request."""
    return _file_response(service.get_artifact(delivery_id, format))


@router.post("/deliveries/{delivery_id}/evidence-pack", response_model=EvidencePackRead, status_code=201)
def build_evidence_pack(
    delivery_id: int,
    service: EvidenceService = Depends(get_evidence_service),
) -> EvidencePackRead:
    """(Re)build the pack from the current decision; the previous pack is kept."""
    return service.build_pack(delivery_id)


@router.get("/deliveries/{delivery_id}/debit-note")
def get_debit_note(
    delivery_id: int,
    service: EvidenceService = Depends(get_evidence_service),
) -> Response:
    """Debit note PDF for a partial_pay verdict; 404 for any other verdict."""
    return _file_response(service.get_artifact(delivery_id, "debit_note"))


@router.get("/evidence/{sha256}/verify", response_model=EvidenceVerifyRead)
def verify_evidence(
    sha256: str,
    service: EvidenceService = Depends(get_evidence_service),
) -> EvidenceVerifyRead:
    return service.verify(sha256)
