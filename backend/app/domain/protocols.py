"""Protocols defined in domain; infra implements them, injected via api/deps."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

from app.domain.schemas.decision_agent import DecisionRecord, ToolTurn

T = TypeVar("T", bound=BaseModel)


@runtime_checkable
class PurchaseOrderRepository(Protocol):
    def list_purchase_orders(self) -> list[Any]: ...

    def get_purchase_order(self, po_id: int) -> Any | None: ...


@runtime_checkable
class RuleRepository(Protocol):
    def create_rule(self, **fields: Any) -> Any: ...

    def get_rule(self, rule_pk: int) -> Any | None: ...

    def list_rules(self, status: str | None = None) -> list[Any]: ...

    def set_status(self, rule_pk: int, status: str) -> Any | None: ...

    def set_conflicts(self, rule_pk: int, conflict_with: list[str]) -> Any | None: ...

    def commit(self) -> None: ...


@runtime_checkable
class SimulationRepository(Protocol):
    """Read-only data for policy simulation. No method may write."""

    def list_rules_for_version(self, policy_version: str, status: str | None = None) -> list[Any]: ...

    def list_purchase_orders(self) -> list[Any]: ...

    def get_grn_line(self, po_line_id: int) -> Any | None: ...

    def get_invoice_line(self, po_line_id: int) -> Any | None: ...

    def get_perception_result(self, po_line_id: int) -> Any | None: ...

    def get_delivery_for_po(self, po_id: int) -> Any | None: ...

    def get_latest_decision(self, po_id: int) -> Any | None: ...

    def is_duplicate_invoice(
        self, *, vendor_id: int, invoice_number: str, exclude_invoice_id: int
    ) -> bool: ...


@runtime_checkable
class CaseRepository(Protocol):
    """Read-only data for the cases read model. No method may write."""

    def list_purchase_orders(self) -> list[Any]: ...

    def get_purchase_order(self, po_id: int) -> Any | None: ...

    def get_vendor(self, vendor_id: int) -> Any | None: ...

    def get_grn_line(self, po_line_id: int) -> Any | None: ...

    def get_invoice_line(self, po_line_id: int) -> Any | None: ...

    def get_perception_result(self, po_line_id: int) -> Any | None: ...

    def get_delivery_for_po(self, po_id: int) -> Any | None: ...

    def get_grn_for_po(self, po_id: int) -> Any | None: ...

    def get_invoice_for_po(self, po_id: int) -> Any | None: ...

    def list_approved_rules(self) -> list[Any]: ...

    def get_delivery(self, delivery_id: int) -> Any | None: ...

    def get_latest_decision(self, po_id: int) -> Any | None: ...

    def list_tracks(self, sam_run_id: int) -> list[Any]: ...

    def is_duplicate_invoice(
        self, *, vendor_id: int, invoice_number: str, exclude_invoice_id: int
    ) -> bool: ...


@runtime_checkable
class DecisionRepository(Protocol):
    """Writes for the decision agent: the decisions row and its job events."""

    def save_decision(self, record: DecisionRecord) -> int: ...

    def append_event(
        self, job_id: str, event_type: str, message: str, payload: dict[str, Any] | None = None
    ) -> None: ...

    def create_decision_job(self, *, delivery_id: int, po_id: int) -> str: ...

    def finish_job(self, job_id: str, *, error_code: str | None = None, message: str | None = None) -> None: ...


@runtime_checkable
class ModelClient(Protocol):
    async def call_model(
        self,
        *,
        purpose: str,
        model: str,
        prompt: str,
        output_schema: type[T],
        reasoning_effort: str | None = None,
        instructions: str | None = None,
    ) -> T: ...

    async def call_video_model(
        self,
        *,
        purpose: str,
        model: str,
        instructions: str,
        user_text: str,
        file_id: str,
        output_schema: type[T],
        reasoning_effort: str | None = None,
    ) -> T: ...

    async def call_tool_turn(
        self,
        *,
        purpose: str,
        model: str,
        instructions: str,
        input_items: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        session: Any | None = None,
        reasoning_effort: str | None = None,
    ) -> ToolTurn: ...

    async def call_image_model(
        self,
        *,
        purpose: str,
        model: str,
        instructions: str,
        user_text: str,
        image_data_urls: list[str],
        output_schema: type[T],
        reasoning_effort: str | None = None,
    ) -> T: ...


@runtime_checkable
class FileStore(Protocol):
    def put_bytes(self, relative_path: str, data: bytes) -> Path: ...

    def read_bytes(self, relative_path: str) -> bytes: ...

    def exists(self, relative_path: str) -> bool: ...


@runtime_checkable
class CacheStore(Protocol):
    def get_bytes(self, key: str) -> bytes | None: ...

    def put_bytes(self, key: str, data: bytes) -> Path: ...
