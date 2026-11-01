"""Evidence packs: PDF + JSON per decided delivery, SHA-256, re-verifiable.

Flow: decide the case through CaseService (live, from approved rules) ->
assemble the pack document in Python -> collect frames -> hash the canonical
JSON bytes (that hash IS the pack hash) -> render the PDF (and a debit-note
PDF for partial_pay) -> store everything -> re-read the stored bytes to set
``verified``. ``verify`` repeats that re-hash at any later time.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.domain.evidence import (
    DEBIT_NAME,
    JSON_NAME,
    PDF_NAME,
    EvidenceRepository,
    FileStore,
    FrameSource,
    PackRenderer,
    build_pack_document,
    canonical_json,
    safe_filename_part,
    sha256_bytes,
)
from app.domain.schemas.dashboard import EvidenceVerifyRead, PolicyRead
from app.domain.schemas.evidence import (
    EvidenceFile,
    EvidenceFrame,
    EvidencePackRead,
    ManifestEntry,
    NewPack,
    PackModels,
    StoredPack,
)
from app.services.cases import CaseService

logger = get_logger(__name__)

ArtifactKind = Literal["pdf", "json", "debit_note"]


def to_read(pack: StoredPack) -> EvidencePackRead:
    """Stored row -> API shape (files = top-level artifacts, frames excluded)."""
    files = [m.name for m in pack.manifest if m.role != "frame"]
    return EvidencePackRead(sha256=pack.sha256, created_at=pack.created_at, verified=pack.verified, files=files)


def latest_pack_for_po(repository: EvidenceRepository, po_id: int) -> EvidencePackRead | None:
    """Newest pack for a PO as {sha256, created_at, verified, files}, or None.

    Cheap (one SELECT, no rendering): attach it to case detail without
    wiring the whole EvidenceService.
    """
    pack = repository.latest_pack_for_po(po_id)
    return to_read(pack) if pack else None


class EvidenceService:
    def __init__(
        self,
        cases: CaseService,
        repository: EvidenceRepository,
        store: FileStore,
        renderer: PackRenderer,
        frames: FrameSource,
        models: PackModels,
        policy_provider: Callable[[], PolicyRead | None],
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._cases = cases
        self._repo = repository
        self._store = store
        self._renderer = renderer
        self._frames = frames
        self._models = models
        self._policy_provider = policy_provider
        self._clock = clock

    # ------------------------------------------------------------ queries
    def latest_pack_for_po(self, po_id: int) -> EvidencePackRead | None:
        return latest_pack_for_po(self._repo, po_id)

    def get_artifact(self, delivery_id: int, kind: ArtifactKind) -> EvidenceFile:
        """Bytes of the latest pack artifact; builds the pack first if none exists."""
        delivery = self._repo.get_delivery(delivery_id)
        if delivery is None:
            raise NotFoundError(f"Delivery {delivery_id} was not found.", code="delivery_not_found")
        pack = self._repo.latest_pack_for_po(delivery.po_id)
        if pack is None:
            self.build_pack(delivery_id)
            pack = self._repo.latest_pack_for_po(delivery.po_id)
        if pack is None:  # pragma: no cover - build_pack raises or stores
            raise NotFoundError("Evidence pack was not built.", code="evidence_pack_not_found")
        role = {"pdf": "pdf", "json": "json", "debit_note": "debit_note"}[kind]
        entry = next((m for m in pack.manifest if m.role == role), None)
        if entry is None:
            if kind == "debit_note":
                raise NotFoundError(
                    "No debit note: debit notes are raised only for partial_pay verdicts.", code="debit_note_not_applicable"
                )
            raise NotFoundError("Evidence pack file is missing.", code="evidence_pack_not_found")
        data = self._store.read_bytes(entry.path)
        stem = safe_filename_part(self._po_number(pack))
        media = "application/json" if kind == "json" else "application/pdf"
        suffix = "json" if kind == "json" else "pdf"
        prefix = "debit-note" if kind == "debit_note" else "evidence-pack"
        return EvidenceFile(name=f"{prefix}_{stem}_{pack.sha256[:8]}.{suffix}", media_type=media, data=data)

    def _po_number(self, pack: StoredPack) -> str:
        try:
            return self._cases.get_case(pack.po_id).po_number
        except NotFoundError:
            return f"po-{pack.po_id}"

    # ------------------------------------------------------------- build
    def build_pack(self, delivery_id: int) -> EvidencePackRead:
        delivery = self._repo.get_delivery(delivery_id)
        if delivery is None:
            raise NotFoundError(f"Delivery {delivery_id} was not found.", code="delivery_not_found")
        case = self._cases.get_case(delivery.po_id)
        if case.verdict is None:
            raise ConflictError(
                f"Purchase order {case.po_number} has no decision yet; an evidence pack needs a verdict.",
                code="case_not_decided",
            )
        generated_at = self._clock()
        decision = self._repo.get_latest_decision(delivery.po_id)
        collection = self._frames.collect(delivery_id=delivery_id, video_path=delivery.video_path)

        frame_refs: list[EvidenceFrame] = []
        frame_bytes: dict[str, bytes] = {}
        for n, image in enumerate(collection.frames, start=1):
            name = f"frames/frame_{n}.jpg"
            frame_bytes[name] = image.jpeg
            frame_refs.append(
                EvidenceFrame(
                    index=n,
                    label=image.label,
                    filename=name,
                    sha256=sha256_bytes(image.jpeg),
                    source=image.source,
                    frame_index=image.frame_index,
                    t_seconds=image.t_seconds,
                )
            )
        document = build_pack_document(
            case=case,
            delivery_id=delivery_id,
            policy=self._policy_provider(),
            decision=decision,
            models=self._models,
            frames=frame_refs,
            frames_note=collection.note,
            video_sha256=collection.video_sha256,
            generated_at=generated_at,
        )
        json_bytes = canonical_json(document)
        pack_sha = sha256_bytes(json_bytes)
        pdf_bytes = self._renderer.render_pack(document, frame_bytes, pack_sha)

        base = f"evidence/po_{case.po_id}/{pack_sha[:16]}"
        manifest: list[ManifestEntry] = []

        def put(name: str, data: bytes, role: Literal["pdf", "json", "debit_note", "frame"]) -> str:
            relative = f"{base}/{name}"
            self._store.put_bytes(relative, data)
            manifest.append(ManifestEntry(name=name, path=relative, sha256=sha256_bytes(data), bytes=len(data), role=role))
            return relative

        json_path = put(JSON_NAME, json_bytes, "json")
        pdf_path = put(PDF_NAME, pdf_bytes, "pdf")
        if document.debit_note is not None:
            put(DEBIT_NAME, self._renderer.render_debit_note(document, pack_sha), "debit_note")
        for name, data in frame_bytes.items():
            put(name, data, "frame")

        stored = self._repo.add_pack(
            NewPack(
                po_id=case.po_id,
                delivery_id=delivery_id,
                decision_id=decision.id if decision else None,
                sha256=pack_sha,
                pdf_path=pdf_path,
                json_path=json_path,
                verified=False,
                manifest=manifest,
            )
        )
        verified = self._files_match(stored.manifest, pack_sha)
        self._repo.set_verified(stored.id, verified)
        logger.info("evidence pack built po=%s sha=%s verified=%s", case.po_number, pack_sha[:12], verified)
        return to_read(stored.model_copy(update={"verified": verified}))

    # ------------------------------------------------------------ verify
    def verify(self, sha256: str) -> EvidenceVerifyRead:
        candidate = sha256.lower()
        if len(candidate) != 64 or any(c not in "0123456789abcdef" for c in candidate):
            raise ValidationError("sha256 must be 64 hexadecimal characters.", code="invalid_sha256")
        pack = self._repo.get_pack_by_sha(candidate)
        if pack is None:
            raise NotFoundError("No evidence pack has that SHA-256.", code="evidence_pack_not_found")
        verified = self._files_match(pack.manifest, pack.sha256)
        self._repo.set_verified(pack.id, verified)
        return EvidenceVerifyRead(sha256=pack.sha256, verified=verified, checked_at=self._clock())

    def _files_match(self, manifest: list[ManifestEntry], pack_sha256: str) -> bool:
        """Re-read every stored file and compare its hash with the recorded one."""
        json_entries = [m for m in manifest if m.role == "json"]
        if len(json_entries) != 1 or json_entries[0].sha256 != pack_sha256:
            return False
        for entry in manifest:
            if not self._store.exists(entry.path):
                return False
            if sha256_bytes(self._store.read_bytes(entry.path)) != entry.sha256:
                return False
        return True
