"""Domain enums. Pure Python, no framework imports."""
from __future__ import annotations

from enum import StrEnum


class JobStatus(StrEnum):
    QUEUED = "queued"
    UPLOADING = "uploading"
    UNDERSTANDING = "understanding"
    TRACKING = "tracking"
    DAMAGE_CHECK = "damage_check"
    DONE = "done"
    FAILED = "failed"


class JobKind(StrEnum):
    PERCEPTION = "perception"
    DECISION = "decision"
    EVIDENCE = "evidence"


class SamRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CACHED = "cached"


class EvidenceQuality(StrEnum):
    RELIABLE = "reliable"
    INSUFFICIENT = "insufficient"


class Verdict(StrEnum):
    APPROVE = "approve"
    HOLD_PAYMENT = "hold_payment"
    HUMAN_REVIEW = "human_review"


class DamageSource(StrEnum):
    SAM = "sam"
    PERCEPTION = "perception"
    HUMAN = "human"
