"""Protocols defined in domain; infra implements them, injected via api/deps."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@runtime_checkable
class PurchaseOrderRepository(Protocol):
    def list_purchase_orders(self) -> list[Any]: ...

    def get_purchase_order(self, po_id: int) -> Any | None: ...


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
