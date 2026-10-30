"""Stage D (damage check) contract: one verdict per tracked object."""
from __future__ import annotations

from pydantic import BaseModel


class DamageVerdict(BaseModel):
    track_id: str
    damaged: bool
    frame_index: int | None = None
    note: str = ""
