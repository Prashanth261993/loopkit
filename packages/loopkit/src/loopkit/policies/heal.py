"""policies/heal.py — self-correction: actor–critic, Reflexion, anti-thrash.

M0 proved the loop runs; M1 made it survivable. M2 makes it *self-correcting*.
When something goes wrong — a tool errors, a test fails, a final answer is
rejected — a naive loop either dies or blindly repeats itself. LoopKit instead
routes the failure through a small **heal** pipeline:

    trigger -> critic reviews -> Reflexion note injected -> retry (bounded)

The pieces are deliberately tiny and pluggable, mirroring the rest of the kit:

  * :class:`HealTrigger` — the taxonomy of *why* we heal (locked v1 set).
  * :class:`Critic`      — turns a failure into a structured :class:`Critique`.
  * :class:`ReflexionMemory` — the durable "what I learned from failing" log
    (Shinn et al. 2023). Its notes are re-injected so the model doesn't repeat
    the same mistake.
  * :class:`HealPolicy` — the *heal budget*: how many corrections we'll fund
    before giving up. Kept separate from the token budget on purpose (see lesson).
  * :class:`Backoff`   — retry spacing (a no-op in tests, exponential in prod).
  * :class:`ThrashDetector` — oscillation guard. Distinct from M1's ``NoProgress``:
    NoProgress halts on *consecutive* repeats; thrash counts *total* repeats of a
    signature so interleaved oscillation ("A B A B A") is caught too.

Everything here is inert unless the caller wires a critic + heal policy into the
Kernel, so M0/M1 event streams stay byte-for-byte identical.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from loopkit.state import KernelState
from loopkit.tools import ToolResult


class HealTrigger(str, Enum):
    """Why a heal fired. v1 is locked to these three; ``low_confidence`` is
    intentionally deferred until we have a calibrated confidence signal."""

    TOOL_ERROR = "tool_error"      # a tool raised / returned ok=False
    TEST_FAIL = "test_fail"        # a tool ran, but its output says tests failed
    CRITIC_REJECT = "critic_reject"  # the critic vetoed an otherwise-final answer


@dataclass
class Critique:
    """A structured failure note — the unit the Reflexion memory stores.

    Structured (not a raw transcript slice) is a deliberate choice: it keeps the
    signal dense, is trivial to render into a prompt, and is machine-inspectable
    for evals/telemetry.
    """

    trigger: HealTrigger
    reason: str
    suggestion: str
    iteration: int

    def as_note(self) -> dict[str, str]:
        """Render into a history message the model will actually read next turn."""
        return {
            "role": "system",
            "name": "reflexion",
            "content": (
                f"[reflexion] iteration {self.iteration} {self.trigger.value}: "
                f"{self.reason}. Next time: {self.suggestion}"
            ),
        }


class Critic(Protocol):
    """Reviews the run and, if it finds a problem, returns a :class:`Critique`.

    Two entry points because the two failure surfaces differ: a tool *result*
    versus a proposed *final answer*.
    """

    name: str

    def inspect_tool(
        self, state: KernelState, tool_result: ToolResult
    ) -> Critique | None: ...

    def inspect_final(self, state: KernelState, final: str) -> Critique | None: ...


class RuleBasedCritic:
    """A deterministic, zero-LLM critic — the CI/eval backbone.

    Keeping a rule-based critic in the box (alongside a future ``LLMCritic``)
    means the whole self-heal machinery is testable without a network call, and
    that heal behaviour is reproducible in evals. Callers inject two optional
    predicates to teach it their domain:

    * ``test_failed(tool_result) -> reason | None`` — detect a failing test run
      inside an otherwise-``ok`` tool result (e.g. a test-runner tool).
    * ``reject_final(answer) -> reason | None`` — veto a final answer (e.g. it
      must cite a value, satisfy a schema, or pass a checker).
    """

    def __init__(
        self,
        *,
        test_failed: Callable[[ToolResult], str | None] | None = None,
        reject_final: Callable[[str], str | None] | None = None,
    ) -> None:
        self._test_failed = test_failed
        self._reject_final = reject_final
        self.name = "rule_based_critic"

    def inspect_tool(
        self, state: KernelState, tool_result: ToolResult
    ) -> Critique | None:
        # A hard error always trips TOOL_ERROR.
        if not tool_result.ok:
            return Critique(
                trigger=HealTrigger.TOOL_ERROR,
                reason=tool_result.error or "tool returned ok=False",
                suggestion=(
                    "the previous tool call failed; revise the arguments or pick "
                    "a different tool rather than repeating the same call"
                ),
                iteration=state.iteration,
            )
        # A successful call may still carry a logical failure (tests red, etc.).
        if self._test_failed is not None:
            reason = self._test_failed(tool_result)
            if reason:
                return Critique(
                    trigger=HealTrigger.TEST_FAIL,
                    reason=reason,
                    suggestion=(
                        "the checks did not pass; address the reported failure "
                        "before declaring success"
                    ),
                    iteration=state.iteration,
                )
        return None

    def inspect_final(self, state: KernelState, final: str) -> Critique | None:
        if self._reject_final is None:
            return None
        reason = self._reject_final(final)
        if reason:
            return Critique(
                trigger=HealTrigger.CRITIC_REJECT,
                reason=f"answer rejected: {reason}",
                suggestion=(
                    "do not finalize yet; fix the issue the critic raised and "
                    "answer again"
                ),
                iteration=state.iteration,
            )
        return None


class HealPolicy:
    """The *heal budget*: caps how many corrections a run may fund.

    This is separate from the token/iteration Governor by design. Token budget
    answers "can we afford another turn?"; heal budget answers "have we corrected
    too many times to still trust this run?". A loop that heals endlessly is just
    a slower infinite loop.
    """

    def __init__(self, max_heals: int = 3) -> None:
        self.max_heals = max_heals
        self.heals_used = 0
        self.name = f"heal_policy(max={max_heals})"

    def should_heal(self, state: KernelState) -> bool:
        return self.heals_used < self.max_heals

    def record(self) -> None:
        self.heals_used += 1

    def snapshot(self) -> dict[str, int]:
        return {"max_heals": self.max_heals, "heals_used": self.heals_used}


@dataclass
class ReflexionMemory:
    """Durable log of critiques for a run (Reflexion; Shinn et al. 2023).

    Every heal appends a :class:`Critique`. The freshest note is injected into
    history at heal time; the full log survives for the ``run.end`` summary and
    lets a compacting context strategy re-surface lessons even after the raw
    error scrolls out of the window.
    """

    keep_last: int = 5
    critiques: list[Critique] = field(default_factory=list)

    def add(self, critique: Critique) -> None:
        self.critiques.append(critique)

    def latest_note(self) -> dict[str, str] | None:
        if not self.critiques:
            return None
        return self.critiques[-1].as_note()

    def notes(self) -> list[dict[str, str]]:
        return [c.as_note() for c in self.critiques[-self.keep_last :]]

    def summary(self) -> dict[str, object]:
        return {
            "count": len(self.critiques),
            "triggers": [c.trigger.value for c in self.critiques],
        }


class Backoff(Protocol):
    """How long to wait before a retry, given the 1-based attempt number."""

    def delay(self, attempt: int) -> float: ...


class NoBackoff:
    """Zero delay — the default, so tests and evals stay fast and deterministic."""

    name = "no_backoff"

    def delay(self, attempt: int) -> float:
        return 0.0


class ExponentialBackoff:
    """``base * factor**(attempt-1)`` capped at ``cap`` seconds.

    The real-world rail: spacing out retries against flaky I/O (rate limits,
    transient network) instead of hammering. Never used by the deterministic
    demos; provided so production callers don't have to hand-roll it.
    """

    def __init__(self, base: float = 0.5, factor: float = 2.0, cap: float = 8.0) -> None:
        self.base = base
        self.factor = factor
        self.cap = cap
        self.name = f"exp_backoff(base={base},cap={cap})"

    def delay(self, attempt: int) -> float:
        raw = self.base * (self.factor ** max(0, attempt - 1))
        return min(self.cap, raw)


class ThrashDetector:
    """Oscillation guard: trip when one action signature recurs ``threshold``×.

    Reuses the M1 ``action_signature`` stream. Unlike ``NoProgress`` (which fires
    only on *consecutive* identical actions), this counts *total* occurrences, so
    an agent flip-flopping between two useless calls ("open, close, open, close")
    is still caught. When it trips, the kernel emits ``thrash.detected`` and stops
    rather than letting the model burn the budget going in circles.
    """

    def __init__(self, threshold: int = 3) -> None:
        self.threshold = threshold
        self.name = f"thrash({threshold})"

    def repeats_of_latest(self, state: KernelState) -> int:
        sigs = state.action_signatures
        if not sigs:
            return 0
        return sigs.count(sigs[-1])

    def check(self, state: KernelState) -> bool:
        return self.repeats_of_latest(state) >= self.threshold
