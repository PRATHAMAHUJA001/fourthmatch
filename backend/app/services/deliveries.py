"""Delivery use cases: create delivery+job, read stored job_events for SSE."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from app.core.config import REPO_ROOT
from app.core.errors import NotFoundError
from app.domain.enums import JobKind, JobStatus
from app.domain.schemas.jobs import DeliveryCreated, JobEventRead
from app.infra.db.models.jobs import Job, JobEvent, append_job_event
from app.infra.db.models.purchasing import Delivery, PurchaseOrder
from app.infra.storage import LocalFileStore


class DeliveryService:
    def __init__(self, session_factory: sessionmaker[Session], storage: LocalFileStore) -> None:
        self._factory = session_factory
        self._storage = storage

    def create_delivery(self, *, po_id: int, video_bytes: bytes, filename: str) -> DeliveryCreated:
        session = self._factory()
        try:
            po = session.get(PurchaseOrder, po_id)
            if po is None:
                raise NotFoundError(f"Purchase order {po_id} was not found.", code="po_not_found")
            delivery = Delivery(po_id=po_id, status="recorded")
            session.add(delivery)
            session.flush()
            suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else "mp4"
            path = self._storage.put_bytes(f"deliveries/{delivery.id}/video.{suffix}", video_bytes)
            delivery.video_path = str(path)
            job = Job(kind=JobKind.PERCEPTION.value, status=JobStatus.QUEUED.value,
                      delivery_id=delivery.id, po_id=po_id)
            session.add(job)
            session.flush()
            append_job_event(session, job.id, JobStatus.QUEUED.value, "job queued",
                             {"delivery_id": delivery.id, "po_id": po_id})
            session.commit()
            return DeliveryCreated(delivery_id=delivery.id, job_id=job.id)
        finally:
            session.close()

    def create_job_for_delivery(self, *, delivery_id: int) -> DeliveryCreated:
        """New job on an existing delivery (eval runs reuse deliveries 1-4)."""
        session = self._factory()
        try:
            delivery = session.get(Delivery, delivery_id)
            if delivery is None:
                raise NotFoundError(f"Delivery {delivery_id} was not found.", code="delivery_not_found")
            job = Job(kind=JobKind.PERCEPTION.value, status=JobStatus.QUEUED.value,
                      delivery_id=delivery.id, po_id=delivery.po_id)
            session.add(job)
            session.flush()
            append_job_event(session, job.id, JobStatus.QUEUED.value, "job queued",
                             {"delivery_id": delivery.id, "po_id": delivery.po_id})
            session.commit()
            return DeliveryCreated(delivery_id=delivery.id, job_id=job.id)
        finally:
            session.close()

    def video_file(self, *, delivery_id: int) -> Path:
        """Stored video for a delivery (path may be relative to repo or storage root)."""
        session = self._factory()
        try:
            delivery = session.get(Delivery, delivery_id)
            if delivery is None:
                raise NotFoundError(f"Delivery {delivery_id} was not found.", code="delivery_not_found")
            raw = delivery.video_path
        finally:
            session.close()
        if raw:
            candidate = Path(raw)
            options = [candidate] if candidate.is_absolute() else [
                candidate, REPO_ROOT / candidate, self._storage.root / candidate]
            for option in options:
                if option.is_file():
                    return option
        raise NotFoundError(f"Delivery {delivery_id} has no stored video.", code="video_not_found")

    def resolve_job(self, *, delivery_id: int, job_id: str | None) -> str:
        session = self._factory()
        try:
            if session.get(Delivery, delivery_id) is None:
                raise NotFoundError(f"Delivery {delivery_id} was not found.", code="delivery_not_found")
            if job_id:
                job = session.get(Job, job_id)
                if job is None or job.delivery_id != delivery_id:
                    raise NotFoundError(f"Job {job_id} was not found.", code="job_not_found")
                return job.id
            job = (
                session.query(Job).filter(Job.delivery_id == delivery_id)
                .order_by(Job.created_at.desc()).first()
            )
            if job is None:
                raise NotFoundError(f"Delivery {delivery_id} has no job.", code="job_not_found")
            return job.id
        finally:
            session.close()

    def events_after(self, *, job_id: str, after_seq: int) -> list[JobEventRead]:
        session = self._factory()
        try:
            rows = (
                session.query(JobEvent).filter(JobEvent.job_id == job_id, JobEvent.seq > after_seq)
                .order_by(JobEvent.seq).all()
            )
            return [JobEventRead.model_validate(r) for r in rows]
        finally:
            session.close()

    def job_status(self, *, job_id: str) -> str | None:
        session = self._factory()
        try:
            job = session.get(Job, job_id)
            return job.status if job else None
        finally:
            session.close()


DeliveryServiceFactory = Callable[[], DeliveryService]
