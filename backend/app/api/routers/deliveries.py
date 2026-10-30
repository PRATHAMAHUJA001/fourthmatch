"""Deliveries API: upload creates delivery+job; SSE streams stored job_events.

No SQL, no model calls here -- pipeline runs as a background task and SSE
only replays rows the pipeline persisted (ARCHITECTURE §3).
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Query, UploadFile
from fastapi.responses import StreamingResponse

from app.api.deps import get_delivery_service, get_pipeline_runner
from app.domain.enums import JobStatus
from app.domain.schemas.jobs import DeliveryCreated
from app.services.deliveries import DeliveryService

router = APIRouter(tags=["deliveries"])

PipelineRunner = Callable[[str, int], Awaitable[dict]]


@router.post("/deliveries", response_model=DeliveryCreated, status_code=201)
async def create_delivery(
    background: BackgroundTasks,
    video: UploadFile = File(...),
    po_id: int = Form(...),
    service: DeliveryService = Depends(get_delivery_service),
    runner: PipelineRunner = Depends(get_pipeline_runner),
) -> DeliveryCreated:
    video_bytes = await video.read()
    created = service.create_delivery(po_id=po_id, video_bytes=video_bytes, filename=video.filename or "video.mp4")
    background.add_task(runner, created.job_id, created.delivery_id)
    return created


@router.get("/deliveries/{delivery_id}/events")
async def stream_events(
    delivery_id: int,
    job_id: str | None = Query(default=None),
    after_seq: int = Query(default=0, ge=0),
    service: DeliveryService = Depends(get_delivery_service),
) -> StreamingResponse:
    resolved_job_id = service.resolve_job(delivery_id=delivery_id, job_id=job_id)

    async def generate() -> AsyncIterator[str]:
        last_seq = after_seq
        while True:
            events = service.events_after(job_id=resolved_job_id, after_seq=last_seq)
            if events:
                for event in events:
                    last_seq = event.seq
                    yield (
                        f"id: {event.seq}\n"
                        f"event: {event.event_type}\n"
                        f"data: {json.dumps(event.model_dump(mode='json'))}\n\n"
                    )
                if events[-1].event_type in (JobStatus.DONE.value, JobStatus.FAILED.value):
                    return
            else:
                status = service.job_status(job_id=resolved_job_id)
                if status in (JobStatus.DONE.value, JobStatus.FAILED.value):
                    return
                yield ": keep-alive\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(generate(), media_type="text/event-stream")
