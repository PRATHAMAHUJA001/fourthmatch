"""Storekeeper voice remark contracts: ASR response, extracted claims, check.

The remark is CONTEXT ONLY. Nothing here may feed a count, a damage flag or a
verdict; the check merely compares what was said with what the video showed.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AsrTurn(BaseModel):
    """One diarized turn (MODEL_NOTES §6). Extra fields from the API are ignored."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    turn_id: str | int | None = Field(default=None, alias="turnId")
    speaker: str | int | None = None
    start_ms: int | None = Field(default=None, alias="startMs")
    end_ms: int | None = Field(default=None, alias="endMs")
    text: str | None = None


class Transcription(BaseModel):
    """Response of POST /asr/transcribe: full transcript plus turns."""

    model_config = ConfigDict(extra="ignore")

    transcript: str
    turns: list[AsrTurn] = Field(default_factory=list)


class RemarkClaim(BaseModel):
    kind: Literal["count", "damage", "other"]
    category: str | None = None
    quantity: int | None = Field(default=None, ge=0)
    text: str = Field(min_length=1)


class RemarkClaims(BaseModel):
    """BULK_MODEL output: claims extracted from the transcript."""

    claims: list[RemarkClaim] = Field(default_factory=list)


class RemarkStatus(StrEnum):
    SUPPORTED = "supported"
    NOT_SUPPORTED = "not_supported"
    NO_CLAIM = "no_claim"
    UNVERIFIABLE = "unverifiable"


class ClaimVerdict(StrEnum):
    SUPPORTED = "supported"
    NOT_SUPPORTED = "not_supported"
    UNVERIFIABLE = "unverifiable"


class LineObservation(BaseModel):
    """What perception saw for one PO line (all numbers computed in Python)."""

    po_line_id: int | None = None
    category: str
    observed_count: int | None = Field(default=None, ge=0)
    damaged_count: int = Field(default=0, ge=0)
    reliable: bool = True  # evidence_quality == reliable


class RemarkItem(BaseModel):
    claim: RemarkClaim
    verdict: ClaimVerdict
    observed: int | None = None  # observed count or damaged count the claim was compared with


class RemarkCheck(BaseModel):
    status: RemarkStatus
    items: list[RemarkItem] = Field(default_factory=list)


class RemarkRead(BaseModel):
    """CaseDetail.remark: the transcript (context, not evidence) and its check."""

    transcript: str
    check: RemarkCheck | None = None
