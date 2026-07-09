"""context.py — the ContextStrategy seam: what the model actually sees.

An agent's ``history`` grows every turn. Left unchecked it blows the context
window, inflates cost, and buries the signal. A :class:`ContextStrategy` decides
which slice of history to hand the model on each iteration — the difference
between a loop that scales to 50 steps and one that dies at 8.

All strategies here are **deterministic and zero-LLM**, so the whole context
pipeline is unit-testable without a model. (A summarizer *could* call an LLM;
the default one is a structured rollup so tests stay hermetic.)

Contract::

    result = strategy.build(state)   # -> ContextResult(messages, dropped, summary)

The kernel feeds ``result.messages`` to the adapter and records
``result.dropped`` / token estimate on ``iteration.start`` so a viewer can see
compaction happening live.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from loopkit.state import KernelState


@dataclass
class ContextResult:
    """The concrete window handed to the model this turn."""

    messages: list[dict]
    dropped: int = 0
    summary: str | None = None
    strategy: str = "passthrough"
    tokens_est: int = 0

    def describe(self) -> dict:
        """Compact payload for the ``iteration.start`` event."""
        return {
            "context_strategy": self.strategy,
            "context_messages": len(self.messages),
            "context_dropped": self.dropped,
            "context_tokens_est": self.tokens_est,
            "context_summarized": self.summary is not None,
        }


@runtime_checkable
class ContextStrategy(Protocol):
    name: str

    def build(self, state: KernelState) -> ContextResult: ...


def estimate_tokens(messages: list[dict]) -> int:
    """~4 chars/token heuristic. Good enough to drive compaction thresholds and
    to give a dashboard a cost curve without tokenizing for real."""
    chars = sum(len(str(m.get("content", ""))) for m in messages)
    return max(0, chars // 4)


def _partition(history: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """Split history into (system messages, first non-system 'head', tail).

    The head is almost always the task — the one message you must never drop.
    System messages carry the instructions/tools preamble, also load-bearing.
    """
    system = [m for m in history if m.get("role") == "system"]
    non_system = [m for m in history if m.get("role") != "system"]
    head = non_system[:1]
    tail = non_system[1:]
    return system, head, tail


class PassthroughContext:
    """Identity strategy — the M0 behaviour. Every message, every turn."""

    name = "passthrough"

    def build(self, state: KernelState) -> ContextResult:
        msgs = list(state.history)
        return ContextResult(
            messages=msgs,
            dropped=0,
            strategy=self.name,
            tokens_est=estimate_tokens(msgs),
        )


class WindowedContext:
    """Keep system + the task + the most recent ``keep_last`` messages.

    The cheapest scaling trick: a sliding window. It forgets the middle
    entirely, which is fine when only recent state matters (most tool loops).
    """

    def __init__(self, keep_last: int = 6) -> None:
        self.keep_last = keep_last
        self.name = f"windowed(keep_last={keep_last})"

    def build(self, state: KernelState) -> ContextResult:
        system, head, tail = _partition(state.history)
        kept_tail = tail[-self.keep_last :] if self.keep_last < len(tail) else tail
        dropped = len(tail) - len(kept_tail)
        msgs = system + head + kept_tail
        return ContextResult(
            messages=msgs,
            dropped=dropped,
            strategy=self.name,
            tokens_est=estimate_tokens(msgs),
        )


def default_summarize(dropped: list[dict]) -> str:
    """Deterministic rollup of the messages we're about to forget.

    Not an LLM call — a structured trace so the model keeps *some* memory of the
    middle (which tools ran, what they returned) without the full transcript.
    Swap in an LLM summarizer for prose; this keeps evals/tests hermetic.
    """
    if not dropped:
        return ""
    tools_used: dict[str, int] = {}
    observations: list[str] = []
    for m in dropped:
        role = m.get("role", "")
        content = str(m.get("content", ""))
        if role == "tool":
            name = str(m.get("name", "tool"))
            tools_used[name] = tools_used.get(name, 0) + 1
            observations.append(f"{name} -> {content[:80]}")
    tool_line = ", ".join(f"{k}×{v}" for k, v in tools_used.items()) or "none"
    lines = [
        f"[compacted {len(dropped)} earlier messages]",
        f"tools invoked: {tool_line}",
    ]
    if observations:
        lines.append("recent observations:")
        lines.extend(f"  - {o}" for o in observations[-5:])
    return "\n".join(lines)


class CompactingContext:
    """Windowed, but the dropped middle is replaced by a summary message.

    This is the strategy that lets a loop run long *and* stay coherent: the
    model still knows roughly what happened before the window, so it doesn't
    repeat work it already did.
    """

    def __init__(
        self,
        keep_last: int = 6,
        summarize: Callable[[list[dict]], str] = default_summarize,
    ) -> None:
        self.keep_last = keep_last
        self.summarize = summarize
        self.name = f"compacting(keep_last={keep_last})"

    def build(self, state: KernelState) -> ContextResult:
        system, head, tail = _partition(state.history)
        kept_tail = tail[-self.keep_last :] if self.keep_last < len(tail) else tail
        dropped_slice = tail[: len(tail) - len(kept_tail)]
        dropped = len(dropped_slice)
        summary: str | None = None
        middle: list[dict] = []
        if dropped:
            summary = self.summarize(dropped_slice)
            middle = [{"role": "system", "name": "context_summary", "content": summary}]
        msgs = system + head + middle + kept_tail
        return ContextResult(
            messages=msgs,
            dropped=dropped,
            summary=summary,
            strategy=self.name,
            tokens_est=estimate_tokens(msgs),
        )


__all__ = [
    "ContextStrategy",
    "ContextResult",
    "PassthroughContext",
    "WindowedContext",
    "CompactingContext",
    "estimate_tokens",
    "default_summarize",
]
