"""Perception pipeline: Stages A-E for one delivery job.

State machine (ARCHITECTURE §3): queued -> uploading -> understanding ->
tracking -> damage_check -> done | failed. Every stage writes a job_event on
start and finish, job row + event in the same transaction. SSE streams only
those stored rows. One pipeline at a time (asyncio.Semaphore(1)); SQLite WAL
lets SSE poll while the pipeline writes.

Caching (all under storage/cache/, keyed by SHA-256):
- Files API uploads by video hash; a file-related 400/404 re-uploads once.
- Stage B by (video sha, PO-lines hash, model, PROMPT_VERSION), so a changed
  noun phrase can never be caused by re-asking the model during tuning --
  and SAM by (video sha, phrase, seg model, proxy fps) independently.
- Stage D by (video sha, phrase, track_id, crop hashes, model, PROMPT_VERSION).
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from app.core.config import REPO_ROOT, Settings
from app.core.errors import AppError, ValidationError
from app.core.logging import get_logger
from app.domain.counting import apply_phrase_coverage, count_line, generic_noun_for
from app.domain.enums import EvidenceQuality, JobStatus
from app.domain.protocols import Transcriber
from app.domain.remark import check_remark, validate_claims
from app.domain.schemas.config import CountingConfig
from app.domain.schemas.damage import DamageVerdict
from app.domain.schemas.perception import PerceptionResult, Track
from app.domain.schemas.remark import (
    LineObservation,
    RemarkCheck,
    RemarkClaims,
    RemarkStatus,
)
from app.domain.schemas.understanding import FootageNeeded, Understanding
from app.infra import audio as audio_lib
from app.infra import video as video_lib
from app.infra.cache import Sha256Cache, cache_key_for, sha256_hex
from app.infra.db.models.jobs import Job, append_job_event
from app.infra.db.models.perception import DamageFlag, SamRun
from app.infra.db.models.perception import PerceptionResult as PerceptionResultRow
from app.infra.db.models.perception import Track as TrackRow
from app.infra.db.models.purchasing import Delivery, PoLine
from app.infra.meta.asr import MetaTranscriber
from app.infra.meta.client import MetaModelClient
from app.infra.meta.sam import SamSegmenter
from app.services.decision_agent import DecisionAgent

logger = get_logger(__name__)

_PIPELINE_SEMAPHORE = asyncio.Semaphore(1)

STAGE_B_PROMPT_VERSION = "stage-b-v2"
STAGE_B_SYSTEM_PROMPT = (
    "You are FourthMatch's receiving-dock perception agent. You get a receiving-dock video and\n"
    "the purchase-order lines that should be in it (category + description). Your only jobs:\n"
    "(1) for each PO line, pick one short, concrete, visual noun phrase a segmentation model can\n"
    "find, describing exactly one object type (good: 'cardboard box', 'white sack', 'steel\n"
    "coil'; bad: 'goods', 'boxes and bags', 'damaged box'). If two lines look alike, pick\n"
    "phrases that separate them by a visible feature. Use the most general noun that covers\n"
    "EVERY unit of that PO line. Add a colour or other feature only when needed to tell two\n"
    "different PO lines apart, never to describe a single line. (2) State scene facts: camera motion,\n"
    "occlusion, lighting, and objects present that match no PO line. Never state or estimate a\n"
    "count. Never judge damage. Return only JSON:\n"
    '{"lines":[{"po_line_id":"","noun_phrase":"","distinguishing_feature":null}],\n'
    '"scene":{"camera_motion":"static|pan|handheld","occlusion":"none|partial|heavy",\n'
    '"lighting":"good|poor","unlisted_objects":[]}}'
)

STAGE_D_PROMPT_VERSION = "stage-d-v1"
STAGE_D_SYSTEM_PROMPT = (
    "You inspect crops of ONE tracked object from a receiving-dock video. Decide if it is\n"
    "visibly damaged: crushed, torn, punctured, wet or spilled. Judge only what the crops show;\n"
    "if no crop shows damage clearly, damaged is false. Cite the frame_index of the crop that\n"
    "shows it. Return only JSON:\n"
    '{"track_id":"","damaged":false,"frame_index":null,"note":""}'
)

FOOTAGE_PROMPT_VERSION = "footage-v1"
FOOTAGE_SYSTEM_PROMPT = (
    "You write exactly one short sentence telling a receiving-dock operator what extra "
    "footage to capture so a delivery can be verified. Use only the facts given. "
    "Return only JSON."
)


REMARK_PROMPT_VERSION = "remark-claims-v1"
REMARK_SYSTEM_PROMPT = (
    "You extract factual claims from a storekeeper's spoken remark about a delivery. Use only\n"
    "what the remark says; never infer. For each claim set kind: 'count' (how many units arrived),\n"
    "'damage' (how many units are damaged), or 'other' (anything else, e.g. lateness). For\n"
    "count/damage claims set category to EXACTLY one of the allowed categories if the remark names\n"
    "or clearly implies one, else null; set quantity to the integer said, else null. Copy the\n"
    "claim's words into text. Return only JSON:\n"
    '{"claims":[{"kind":"count|damage|other","category":null,"quantity":null,"text":""}]}'
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class PerceptionPipeline:
    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker[Session],
        *,
        model_client: MetaModelClient | None = None,
        sam: SamSegmenter | None = None,
        decision_agent: DecisionAgent | None = None,
        run_decision: bool = True,
        transcriber: Transcriber | None = None,
    ) -> None:
        self._settings = settings
        self._factory = session_factory
        self._cache = Sha256Cache(settings.cache_root)
        config = settings.model_config_model()
        self._model = model_client or MetaModelClient(config, cache=self._cache)
        self._sam = sam or SamSegmenter(config, settings.cache_root)
        self._config = config
        self._transcriber: Transcriber = transcriber or MetaTranscriber(
            config, session_factory=session_factory, cache=self._cache
        )
        self._decision_agent: DecisionAgent | None = None
        if run_decision:
            self._decision_agent = decision_agent or DecisionAgent(
                session_factory, self._model, config.decision_model, max_turns=settings.max_agent_turns
            )
        self._counting = CountingConfig(
            sam_score_min=settings.sam_score_min,
            min_track_seconds=settings.min_track_seconds,
            merge_max_gap_seconds=settings.merge_max_gap_seconds,
            merge_min_iou=settings.merge_min_iou,
            max_short_track_ratio=settings.max_short_track_ratio,
            max_merge_ratio=settings.max_merge_ratio,
            proxy_fps=settings.sam_proxy_fps,
        )

    # ------------------------------------------------------------ job state
    def _transition(self, job_id: str, status: JobStatus, progress: int, message: str,
                    payload: dict[str, Any] | None = None, *, event_suffix: str = "") -> None:
        session = self._factory()
        try:
            job = session.get(Job, job_id)
            if job is None:
                return
            job.status = status.value
            job.current_step = status.value
            job.progress_pct = progress
            if status is JobStatus.UPLOADING and job.started_at is None:
                job.started_at = _utcnow()
            append_job_event(session, job_id, f"{status.value}{event_suffix}", message, payload or {})
            session.commit()
        finally:
            session.close()

    def _event(self, job_id: str, event_type: str, message: str, payload: dict[str, Any] | None = None) -> None:
        session = self._factory()
        try:
            append_job_event(session, job_id, event_type, message, payload or {})
            session.commit()
        finally:
            session.close()

    def _fail(self, job_id: str, code: str, message: str) -> None:
        session = self._factory()
        try:
            job = session.get(Job, job_id)
            if job is not None:
                job.status = JobStatus.FAILED.value
                job.error_code = code
                job.error_message = message
                job.finished_at = _utcnow()
                append_job_event(session, job_id, JobStatus.FAILED.value, message, {"error_code": code})
                for run in session.query(SamRun).filter(SamRun.job_id == job_id, SamRun.status == "running").all():
                    run.status = "failed"
                session.commit()
        finally:
            session.close()

    # ---------------------------------------------------------------- run
    async def run(self, job_id: str, delivery_id: int) -> dict[str, Any]:
        async with _PIPELINE_SEMAPHORE:
            return await self._run(job_id, delivery_id)

    async def _run(self, job_id: str, delivery_id: int) -> dict[str, Any]:
        summary: dict[str, Any] = {"delivery_id": delivery_id, "job_id": job_id, "cache": {}}
        try:
            session = self._factory()
            try:
                delivery = session.get(Delivery, delivery_id)
                if delivery is None:
                    raise ValidationError(f"delivery {delivery_id} not found", code="delivery_not_found")
                po_lines = (
                    session.query(PoLine).filter(PoLine.po_id == delivery.po_id)
                    .order_by(PoLine.line_no).all()
                )
                line_inputs = [
                    {"po_line_id": str(line.id), "category": line.category, "description": line.description}
                    for line in po_lines
                ]
                line_by_id = {str(line.id): line for line in po_lines}
                video_path = self._resolve_video_path(delivery.video_path)
                remark_audio = delivery.remark_audio_path
            finally:
                session.close()

            # ---- Stage A: uploading
            self._transition(job_id, JobStatus.UPLOADING, 5, "uploading started")
            video_bytes = video_path.read_bytes()
            video_sha = sha256_hex(video_bytes)
            file_id, upload_hit = await self._sam.upload_cached(video_bytes, video_path.name)
            session = self._factory()
            try:
                delivery_row = session.get(Delivery, delivery_id)
                if delivery_row is not None:
                    delivery_row.video_file_id = file_id
                    session.commit()
            finally:
                session.close()
            summary["cache"]["upload"] = "hit" if upload_hit else "miss"
            self._transition(job_id, JobStatus.UPLOADING, 15, "uploading finished",
                             {"video_sha256": video_sha, "file_id": file_id, "cache_hit": upload_hit},
                             event_suffix="_finished")

            # ---- Remark: transcribe the storekeeper's voice note (context only, optional)
            transcript: str | None = None
            if remark_audio:
                transcript = await self._transcribe_remark(job_id, delivery_id, remark_audio)

            # ---- Stage B: understanding
            self._transition(job_id, JobStatus.UNDERSTANDING, 25, "understanding started")
            understanding = await self._understand(job_id, video_sha, file_id, video_bytes, line_inputs,
                                                   remark=transcript)
            valid_ids = set(line_by_id)
            cited = {line.po_line_id for line in understanding.lines}
            if not cited <= valid_ids or cited != valid_ids:
                raise ValidationError(
                    f"understanding cited unknown/missing po_line_ids: cited={sorted(cited)} valid={sorted(valid_ids)}",
                    code="model_output_invalid",
                )
            summary["scene"] = understanding.scene.model_dump(mode="json")
            summary["cache"]["understanding"] = getattr(self, "_last_b_hit", "miss")
            self._transition(job_id, JobStatus.UNDERSTANDING, 40, "understanding finished",
                             {"lines": [line.model_dump() for line in understanding.lines],
                              "scene": understanding.scene.model_dump(mode="json"),
                              "cache_hit": summary["cache"]["understanding"] == "hit"},
                             event_suffix="_finished")

            # ---- Stage C: tracking (SAM + pure counting)
            self._transition(job_id, JobStatus.TRACKING, 50, "tracking started")
            delivery_root = self._settings.storage_root / "deliveries" / str(delivery_id)
            proxy_path = video_lib.make_proxy(video_path, delivery_root / "proxy.mp4", self._counting.proxy_fps)
            _w, _h, total_frames = video_lib.probe_video(proxy_path)
            line_states: list[dict[str, Any]] = []
            sam_hits: dict[str, str] = {}
            for u_line in understanding.lines:
                po_line = line_by_id[u_line.po_line_id]
                state = await self._track_line(
                    job_id=job_id, delivery_id=delivery_id, po_line=po_line,
                    phrase=u_line.noun_phrase, video_sha=video_sha,
                    proxy_path=proxy_path, total_frames=total_frames,
                )
                line_states.append(state)
                sam_hits[u_line.noun_phrase] = "hit" if state["sam_cache_hit"] else "miss"
                if state["generic_noun"]:
                    sam_hits[state["generic_noun"]] = "hit" if state["generic_cache_hit"] else "miss"
            summary["cache"]["sam"] = sam_hits
            self._transition(job_id, JobStatus.TRACKING, 65, "tracking finished",
                             {"sam_cache": sam_hits}, event_suffix="_finished")

            # ---- footage_needed for insufficient lines (text-only, after C)
            for state in line_states:
                count = state["count"]
                if count.evidence_quality is EvidenceQuality.INSUFFICIENT:
                    state["footage_needed"] = await self._footage_needed(
                        video_sha=video_sha, state=state, scene=understanding.scene.model_dump(mode="json")
                    )
                else:
                    state["footage_needed"] = None

            # ---- Stage D: damage check
            self._transition(job_id, JobStatus.DAMAGE_CHECK, 75, "damage_check started")
            frame_paths = video_lib.extract_frames(proxy_path, delivery_root / "frames")
            damage_hits: dict[str, str] = {}
            for state in line_states:
                damaged, hits = await self._damage_check(
                    video_sha=video_sha, delivery_id=delivery_id, state=state, frame_paths=frame_paths
                )
                state["damaged_track_ids"] = damaged
                damage_hits.update(hits)
            summary["cache"]["damage"] = damage_hits
            self._transition(job_id, JobStatus.DAMAGE_CHECK, 85, "damage_check finished",
                             {"damage_cache": damage_hits}, event_suffix="_finished")

            # ---- Stage E: overlay + annotated MP4, persist results
            self._event(job_id, "rendering", "rendering started")
            results: list[PerceptionResult] = []
            for state in line_states:
                overlay_dir = delivery_root / f"overlay_line_{state['po_line'].id}"
                overlay_frames = video_lib.render_overlay_frames(
                    frame_paths, state["count"].merged_tracks, overlay_dir,
                    mask_image_for_ref=self._sam.mask_image,
                )
                annotated = video_lib.encode_mp4(overlay_frames, overlay_dir / "annotated.mp4",
                                                 fps=self._counting.proxy_fps)
                state["annotated_mp4"] = str(annotated)
                result = self._persist_line(job_id, delivery_id, state)
                results.append(result)
            self._event(job_id, "rendering", "rendering finished",
                        {"annotated_mp4": [s["annotated_mp4"] for s in line_states]})

            summary["results"] = [
                {
                    **result.model_dump(mode="json"),
                    "phrase_observed_count": state["phrase_observed"],
                    "generic_noun": state["generic_noun"],
                    "generic_observed_count": state["generic_observed"],
                }
                for result, state in zip(results, line_states, strict=True)
            ]
            if transcript:
                await self._check_remark(job_id, delivery_id, transcript, results, line_by_id)
            await self._run_decision(job_id, delivery_id)
            session = self._factory()
            try:
                job = session.get(Job, job_id)
                if job is not None:
                    job.status = JobStatus.DONE.value
                    job.current_step = JobStatus.DONE.value
                    job.progress_pct = 100
                    job.finished_at = _utcnow()
                    job.result = summary
                    append_job_event(session, job_id, JobStatus.DONE.value, "done",
                                     {"results": len(results)})
                    session.commit()
            finally:
                session.close()
            return summary
        except AppError as exc:
            self._fail(job_id, exc.code, exc.message)
            raise
        except Exception as exc:  # noqa: BLE001 - job must land in failed, no stack to client
            logger.exception("pipeline failed", extra={"extra_data": {"job_id": job_id}})
            self._fail(job_id, "internal_error", f"pipeline failed: {type(exc).__name__}")
            raise

    # ------------------------------------------------------------- remark
    async def _transcribe_remark(self, job_id: str, delivery_id: int, audio_path: str) -> str | None:
        """Stage: transcribing_remark. Optional: any failure is an event, never a failed job."""
        self._transition(job_id, JobStatus.TRANSCRIBING_REMARK, 18, "transcribing_remark started")
        try:
            src = self._resolve_video_path(audio_path)
            wav = audio_lib.to_wav_16k_mono(src, src.with_name("remark_16k.wav"))
            result = await self._transcriber.transcribe(
                wav=wav.read_bytes(), filename="remark.wav", session_id=f"delivery-{delivery_id}"
            )
        except Exception as exc:  # noqa: BLE001 - the remark is optional context
            logger.exception("remark transcription failed", extra={"extra_data": {"job_id": job_id}})
            self._event(job_id, "transcribing_remark_failed", f"remark not transcribed: {type(exc).__name__}",
                        {"error_code": getattr(exc, "code", "internal_error")})
            return None
        transcript = result.transcript.strip()
        session = self._factory()
        try:
            row = session.get(Delivery, delivery_id)
            if row is not None:
                row.remark_transcript = transcript or None
                session.commit()
        finally:
            session.close()
        self._transition(job_id, JobStatus.TRANSCRIBING_REMARK, 22, "transcribing_remark finished",
                         {"chars": len(transcript)}, event_suffix="_finished")
        return transcript or None

    async def _check_remark(self, job_id: str, delivery_id: int, transcript: str,
                            results: list[PerceptionResult], line_by_id: dict[str, PoLine]) -> None:
        """Extract claims (BULK_MODEL), compare in Python with perception, persist. Non-fatal."""
        try:
            categories = sorted({line.category for line in line_by_id.values()})
            prompt = (
                f"{REMARK_SYSTEM_PROMPT}\nAllowed categories: {json.dumps(categories)}.\n"
                f"Remark transcript: {json.dumps(transcript)}"
            )
            cache_key = cache_key_for(transcript, ",".join(categories), self._config.bulk_model,
                                      REMARK_PROMPT_VERSION)
            session = self._factory()
            try:
                claims = await self._model.call_model(
                    purpose="remark_claims", model=self._config.bulk_model, prompt=prompt,
                    output_schema=RemarkClaims, session=session, cache_key=cache_key,
                )
            finally:
                session.close()
            claims = validate_claims(claims, categories)
            observations = [
                LineObservation(
                    po_line_id=r.po_line_id, category=r.category, observed_count=r.observed_count,
                    damaged_count=len(r.damaged_track_ids),
                    reliable=r.evidence_quality is EvidenceQuality.RELIABLE,
                )
                for r in results
            ]
            check = check_remark(claims, observations)
        except Exception as exc:  # noqa: BLE001 - context only; perception results are stored
            logger.exception("remark check failed", extra={"extra_data": {"job_id": job_id}})
            self._event(job_id, "remark_check_failed", f"remark not checked: {type(exc).__name__}",
                        {"error_code": getattr(exc, "code", "internal_error")})
            check = RemarkCheck(status=RemarkStatus.UNVERIFIABLE, items=[])
        session = self._factory()
        try:
            row = session.get(Delivery, delivery_id)
            if row is not None:
                row.remark_check = check.model_dump(mode="json")
                session.commit()
        finally:
            session.close()
        self._event(job_id, "remark_checked", f"remark {check.status.value}", {"status": check.status.value})

    async def _run_decision(self, job_id: str, delivery_id: int) -> None:
        """Payment decision after perception; its failure never fails the job."""
        if self._decision_agent is None:
            return
        try:
            await self._decision_agent.run(delivery_id, job_id=job_id)
        except Exception as exc:  # noqa: BLE001 - perception results are already stored
            logger.exception("decision failed", extra={"extra_data": {"job_id": job_id}})
            self._event(job_id, "decision_failed", f"decision not recorded: {type(exc).__name__}",
                        {"error_code": getattr(exc, "code", "internal_error")})

    # ------------------------------------------------------------- stages
    def _resolve_video_path(self, video_path: str | None) -> Path:
        if not video_path:
            raise ValidationError("delivery has no video_path", code="delivery_not_found")
        candidate = Path(video_path)
        if candidate.exists():
            return candidate
        for base in (REPO_ROOT, self._settings.storage_root):
            alt = base / video_path
            if alt.exists():
                return alt
        raise ValidationError(f"video file not found: {video_path}", code="delivery_not_found")

    async def _understand(self, job_id: str, video_sha: str, file_id: str,
                          video_bytes: bytes, line_inputs: list[dict[str, Any]],
                          remark: str | None = None) -> Understanding:
        lines_hash = cache_key_for(json.dumps(line_inputs, sort_keys=True))
        key_parts = [video_sha, lines_hash, self._config.perception_model, STAGE_B_PROMPT_VERSION]
        user_text = f"PO lines: {json.dumps(line_inputs)}. Return JSON."
        if remark:
            # Context only: appended so a delivery without a remark keeps its exact prompt and cache key.
            key_parts.append(cache_key_for(remark))
            user_text = (
                f"{user_text} Storekeeper remark, unverified: {json.dumps(remark)}. Use it only as context "
                "for scene facts; it must not change which phrase you choose for a line, and you must "
                "never state a count or judge damage from it."
            )
        cache_key = cache_key_for(*key_parts)
        self._last_b_hit = "hit" if self._cache.get_json(cache_key) is not None else "miss"
        session = self._factory()
        try:
            try:
                return await self._model.call_video_model(
                    purpose="understanding", model=self._config.perception_model,
                    instructions=STAGE_B_SYSTEM_PROMPT, user_text=user_text, file_id=file_id,
                    output_schema=Understanding, session=session, cache_key=cache_key,
                )
            except AppError as exc:
                if exc.code != "model_file_expired":
                    raise
                # Cached file_id expired (MODEL_NOTES §8): re-upload once, retry once.
                self._sam.invalidate_file(video_bytes)
                new_file_id, _ = await self._sam.upload_cached(video_bytes, "video.mp4")
                return await self._model.call_video_model(
                    purpose="understanding", model=self._config.perception_model,
                    instructions=STAGE_B_SYSTEM_PROMPT, user_text=user_text, file_id=new_file_id,
                    output_schema=Understanding, session=session, cache_key=cache_key,
                )
        finally:
            session.close()

    async def _track_line(self, *, job_id: str, delivery_id: int, po_line: PoLine, phrase: str,
                          video_sha: str, proxy_path: Path, total_frames: int) -> dict[str, Any]:
        phrase_state = await self._sam_count(
            job_id=job_id, delivery_id=delivery_id, po_line=po_line, phrase=phrase,
            video_sha=video_sha, proxy_path=proxy_path, total_frames=total_frames,
        )
        generic_noun = generic_noun_for(po_line.category, self._settings.category_generic_nouns)
        generic_state: dict[str, Any] | None = None
        if generic_noun and generic_noun.strip().lower() != phrase.strip().lower():
            generic_state = await self._sam_count(
                job_id=job_id, delivery_id=delivery_id, po_line=po_line, phrase=generic_noun,
                video_sha=video_sha, proxy_path=proxy_path, total_frames=total_frames,
            )
        phrase_count = phrase_state["count"]
        generic_count = generic_state["count"] if generic_state else None
        chosen = apply_phrase_coverage(phrase_count, generic_count)
        generic_won = bool(generic_count and generic_count.observed_count > phrase_count.observed_count)
        chosen_state = generic_state if generic_won and generic_state else phrase_state
        chosen_run_id = int(chosen_state["sam_run_id"])

        # Persist tracks only under the run whose count is used (Stage D/E read these).
        session = self._factory()
        try:
            track_row_ids: dict[str, int] = {}
            for track in chosen.merged_tracks:
                row = TrackRow(
                    delivery_id=delivery_id, sam_run_id=chosen_run_id, object_id=track.track_id,
                    prompt=chosen_state["phrase"], category=po_line.category,
                    first_frame=track.first_frame, last_frame=track.last_frame,
                    frame_count=len(track.frames), confidence=track.mean_score,
                )
                session.add(row)
                session.flush()
                track_row_ids[track.track_id] = row.id
            session.commit()
        finally:
            session.close()
        for position, track in enumerate(chosen.merged_tracks, start=1):
            self._event(job_id, "tracking_progress", f"track {track.track_id} confirmed",
                        {"po_line_id": po_line.id, "tracks": position,
                         "track_id": track.track_id, "phrase": chosen_state["phrase"]})
        return {
            "po_line": po_line, "phrase": phrase, "sam_run_id": chosen_run_id,
            "count": chosen, "sam_cache_hit": bool(phrase_state["outcome"]["cache_hit"]),
            "generic_noun": generic_noun,
            "generic_sam_run_id": generic_state["sam_run_id"] if generic_state else None,
            "generic_cache_hit": bool(generic_state["outcome"]["cache_hit"]) if generic_state else None,
            "phrase_observed": phrase_count.observed_count,
            "generic_observed": generic_count.observed_count if generic_count else None,
            "track_row_ids": track_row_ids, "damaged_track_ids": [],
            "footage_needed": None, "annotated_mp4": None,
        }

    async def _sam_count(self, *, job_id: str, delivery_id: int, po_line: PoLine, phrase: str,
                         video_sha: str, proxy_path: Path, total_frames: int) -> dict[str, Any]:
        """One SAM run (cached) + pure count for a single phrase."""
        session = self._factory()
        try:
            # sam_runs' unique key IS the SAM cache key (video_sha, prompt,
            # model, proxy fps): a re-run reuses that provenance row and
            # replaces its tracks, never inserting a duplicate.
            run = (
                session.query(SamRun)
                .filter(SamRun.video_sha256 == video_sha, SamRun.prompt == phrase,
                        SamRun.seg_model == self._config.seg_model,
                        SamRun.proxy_fps == self._counting.proxy_fps)
                .one_or_none()
            )
            if run is None:
                run = SamRun(
                    delivery_id=delivery_id, job_id=job_id, video_sha256=video_sha,
                    seg_model=self._config.seg_model, prompt=phrase, category=po_line.category,
                    proxy_fps=self._counting.proxy_fps, status="running",
                )
                session.add(run)
            else:
                run.delivery_id = delivery_id
                run.job_id = job_id
                run.status = "running"
                for old_track in list(run.tracks):
                    session.delete(old_track)
            session.commit()
            run_id = run.id
        finally:
            session.close()

        session = self._factory()
        try:
            outcome = await self._sam.segment(
                proxy_path=proxy_path, phrase=phrase, video_sha256=video_sha,
                proxy_fps=self._counting.proxy_fps, total_frames=total_frames, session=session,
            )
        finally:
            session.close()
        count = count_line(outcome["tracks"], self._counting, total_frames=outcome["total_frames"])

        session = self._factory()
        try:
            run_row = session.get(SamRun, run_id)
            if run_row is not None:
                run_row.status = "cached" if outcome["cache_hit"] else "completed"
                run_row.distinct_track_count = count.observed_count
                run_row.raw_cache_path = outcome["raw_cache_path"]
                run_row.video_file_id = outcome["file_id"]
                run_row.finished_at = _utcnow()
            session.commit()
        finally:
            session.close()
        return {"phrase": phrase, "sam_run_id": run_id, "count": count, "outcome": outcome}

    async def _footage_needed(self, *, video_sha: str, state: dict[str, Any],
                              scene: dict[str, Any]) -> str:
        count = state["count"]
        cache_key = cache_key_for(
            video_sha, str(state["po_line"].id), ",".join(count.reasons),
            self._config.perception_model, FOOTAGE_PROMPT_VERSION,
        )
        prompt = (
            f"{FOOTAGE_SYSTEM_PROMPT}\nFacts: category={state['po_line'].category}, "
            f"noun_phrase={state['phrase']}, reason_codes={count.reasons}, scene={json.dumps(scene)}. "
            'Return JSON: {"footage_needed": "..."}'
        )
        session = self._factory()
        try:
            result = await self._model.call_model(
                purpose="footage_needed", model=self._config.perception_model,
                prompt=prompt, output_schema=FootageNeeded, session=session, cache_key=cache_key,
            )
        finally:
            session.close()
        return result.footage_needed

    async def _damage_check(self, *, video_sha: str, delivery_id: int, state: dict[str, Any],
                            frame_paths: list[Path]) -> tuple[list[str], dict[str, str]]:
        damaged: list[str] = []
        hits: dict[str, str] = {}
        session = self._factory()
        try:
            for track in state["count"].merged_tracks:
                verdict, hit = await self._damage_for_track(video_sha, state, track, frame_paths, session)
                hits[f"{state['phrase']}:{track.track_id}"] = hit
                if verdict.damaged:
                    damaged.append(track.track_id)
                    row_id = state["track_row_ids"].get(track.track_id)
                    if row_id is not None:
                        session.add(DamageFlag(
                            track_id=row_id, delivery_id=delivery_id,
                            frame_index=verdict.frame_index, reason_code="visible_damage",
                            source="perception",
                        ))
                        session.commit()
        finally:
            session.close()
        return damaged, hits

    async def _damage_for_track(self, video_sha: str, state: dict[str, Any], track: Track,
                                frame_paths: list[Path], session: Session) -> tuple[DamageVerdict, str]:
        frames = track.frames
        picks: list[int] = []
        for candidate in (0, len(frames) // 2, max(range(len(frames)), key=lambda i: frames[i].score or 0.0)):
            if candidate not in picks:
                picks.append(candidate)
        chosen = [frames[i] for i in picks]
        data_urls: list[str] = []
        crop_hashes: list[str] = []
        labels: list[str] = []
        for frame in chosen:
            url, digest = video_lib.crop_data_url(frame_paths[frame.frame_index], frame.bbox)
            data_urls.append(url)
            crop_hashes.append(digest)
            labels.append(f"track_id={track.track_id} frame_index={frame.frame_index}")
        cache_key = cache_key_for(
            video_sha, state["phrase"], track.track_id, ",".join(crop_hashes),
            self._config.perception_model, STAGE_D_PROMPT_VERSION,
        )
        hit = "hit" if self._cache.get_json(cache_key) is not None else "miss"
        user_text = (
            f"Inspect crops of ONE tracked object. track_id={track.track_id}. "
            f"Crop labels in order: {labels}. Return JSON for track_id {track.track_id}."
        )
        verdict = await self._model.call_image_model(
            purpose="damage_check", model=self._config.perception_model,
            instructions=STAGE_D_SYSTEM_PROMPT, user_text=user_text,
            image_data_urls=data_urls, output_schema=DamageVerdict,
            session=session, cache_key=cache_key,
        )
        # Python rejects any ID the model cites that was not in the input.
        allowed_frames = {f.frame_index for f in chosen}
        if verdict.track_id != track.track_id:
            raise ValidationError(
                f"damage verdict cited unknown track_id {verdict.track_id!r}", code="model_output_invalid"
            )
        if verdict.frame_index is not None and verdict.frame_index not in allowed_frames:
            raise ValidationError(
                f"damage verdict cited unknown frame_index {verdict.frame_index}", code="model_output_invalid"
            )
        if verdict.damaged and verdict.frame_index is None:
            raise ValidationError("damaged verdict must cite a frame_index", code="model_output_invalid")
        return verdict, hit

    def _persist_line(self, job_id: str, delivery_id: int, state: dict[str, Any]) -> PerceptionResult:
        count = state["count"]
        result = PerceptionResult(
            delivery_id=delivery_id, po_line_id=state["po_line"].id, sam_run_id=state["sam_run_id"],
            category=state["po_line"].category, noun_phrase=state["phrase"],
            observed_count=count.observed_count, max_visible=count.max_visible,
            per_frame_counts=count.per_frame_counts, damaged_track_ids=state["damaged_track_ids"],
            evidence_quality=count.evidence_quality, reasons=count.reasons,
            footage_needed=state["footage_needed"],
        )
        session = self._factory()
        try:
            existing = (
                session.query(PerceptionResultRow)
                .filter(PerceptionResultRow.sam_run_id == state["sam_run_id"],
                        PerceptionResultRow.po_line_id == state["po_line"].id)
                .one_or_none()
            )
            if existing is not None:
                session.delete(existing)
                session.flush()
            session.add(PerceptionResultRow(**result.model_dump()))
            session.commit()
        finally:
            session.close()
        return result


PipelineFactory = Callable[[], PerceptionPipeline]
