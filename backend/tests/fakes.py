"""FakeModelClient: replays scripted tool-call turns. No network, no model."""
from __future__ import annotations

import json
from typing import Any

from app.core.errors import UpstreamModelError
from app.domain.schemas.decision_agent import ToolCall, ToolTurn

Step = tuple[str, dict[str, Any]]  # (tool name, arguments)


class FakeModelClient:
    """Each script entry is one model turn: a list of (tool, args) calls.

    An entry of ``Exception`` instance is raised instead; an empty list is a
    turn with no tool call (plain text). Records every request it receives.
    """

    def __init__(self, script: list[list[Step] | Exception]) -> None:
        self._script = list(script)
        self.requests: list[dict[str, Any]] = []
        self._counter = 0

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
    ) -> ToolTurn:
        self.requests.append({
            "purpose": purpose, "model": model, "instructions": instructions,
            "input_items": list(input_items), "tools": tools, "effort": reasoning_effort,
        })
        if not self._script:
            raise AssertionError("FakeModelClient script exhausted")
        entry = self._script.pop(0)
        if isinstance(entry, Exception):
            raise entry
        calls: list[ToolCall] = []
        items: list[dict[str, Any]] = [{"type": "reasoning", "id": f"rs_{self._counter}"}]
        for name, args in entry:
            self._counter += 1
            call_id = f"call_{self._counter}"
            raw = json.dumps(args)
            calls.append(ToolCall(name=name, arguments=raw, call_id=call_id))
            items.append({"type": "function_call", "name": name, "arguments": raw, "call_id": call_id})
        return ToolTurn(output_items=items, calls=calls, output_text="" if entry else "done")

    async def call_model(self, **_kw: Any) -> Any:  # pragma: no cover - unused Protocol members
        raise AssertionError("not used")

    async def call_video_model(self, **_kw: Any) -> Any:  # pragma: no cover
        raise AssertionError("not used")

    async def call_image_model(self, **_kw: Any) -> Any:  # pragma: no cover
        raise AssertionError("not used")


def upstream_error() -> Exception:
    return UpstreamModelError("boom", code="model_upstream")
