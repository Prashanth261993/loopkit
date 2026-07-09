"""adapters/mock.py — a deterministic, zero-LLM adapter.

The MockAdapter replays a pre-scripted sequence of :class:`ModelResult`s. It is
the backbone of LoopKit's testability story: because the model is just another
pluggable adapter, we can exercise the *entire* loop — tool calls, safety
dry-runs, stop policies, the full event stream — without any network or keys.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from loopkit.adapters.base import ModelResult, ToolCall


def act(name: str, args: dict[str, Any], thought: str | None = None) -> ModelResult:
    """Script step: the agent calls a tool."""
    return ModelResult(
        text=thought or f"call {name}",
        thought=thought,
        tool_call=ToolCall(name=name, args=args),
        tokens_in=32,
        tokens_out=16,
    )


def final(answer: str, thought: str | None = None) -> ModelResult:
    """Script step: the agent gives its final answer."""
    return ModelResult(
        text=answer,
        thought=thought,
        final=answer,
        tokens_in=32,
        tokens_out=12,
    )


class MockAdapter:
    """Return scripted results in order. Raises if the loop asks for more turns
    than were scripted — a loud signal that a policy failed to terminate."""

    name = "mock"

    def __init__(self, script: Iterable[ModelResult]) -> None:
        self._script = list(script)
        self._i = 0

    def complete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> ModelResult:
        if self._i >= len(self._script):
            raise RuntimeError(
                "MockAdapter script exhausted: the loop ran more iterations than "
                "were scripted (did a stop policy fail to fire?)."
            )
        result = self._script[self._i]
        self._i += 1
        return result
