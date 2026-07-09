"""adapters/base.py — the model boundary.

A :class:`ModelAdapter` is the ONLY place LoopKit talks to an LLM. The kernel
never sees provider-specific shapes; it sees a normalized :class:`ModelResult`.
This is what lets the same loop drive OpenAI, Ollama, Anthropic, or a scripted
mock — and what lets us test the entire runtime with zero network calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class ToolCall:
    """A normalized request to run a tool, however the model expressed it
    (native function-calling JSON or prompt-based ReAct text)."""

    name: str
    args: dict[str, Any]


@dataclass
class ModelResult:
    """The normalized output of one model turn.

    Exactly one of ``tool_call`` or ``final`` is expected to be set: the agent
    either acts (tool_call) or answers (final). ``thought`` is the reasoning
    trace; token counts feed the Governor and the cost curve on the dashboard.
    """

    text: str
    thought: str | None = None
    tool_call: ToolCall | None = None
    final: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0


class ModelAdapter(Protocol):
    name: str

    def complete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> ModelResult: ...
