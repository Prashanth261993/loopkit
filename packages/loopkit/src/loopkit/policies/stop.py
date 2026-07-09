"""policies/stop.py — composable termination.

Termination is the heart of loop engineering: an agent that can't stop is a
liability. LoopKit models stopping as a set of small, independent policies that
are OR-combined by :class:`AnyOf`. Each policy answers one question and returns
a :class:`StopDecision` only when it wants to halt the run.

The kernel also stops when the model returns a ``final`` answer; these policies
cover the *involuntary* exits (budget, iteration cap, no-progress).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from loopkit.events import RunStatus
from loopkit.state import KernelState


@dataclass
class StopDecision:
    status: RunStatus
    reason: str
    policy: str


class StopPolicy(Protocol):
    name: str

    def check(self, state: KernelState) -> StopDecision | None: ...


class MaxIterations:
    """Halt after ``n`` iterations. The most basic safety net."""

    def __init__(self, n: int) -> None:
        self.n = n
        self.name = f"max_iterations({n})"

    def check(self, state: KernelState) -> StopDecision | None:
        if state.iteration >= self.n:
            return StopDecision(
                status=RunStatus.MAX_ITERS,
                reason=f"reached iteration cap of {self.n}",
                policy=self.name,
            )
        return None


class TokenBudget:
    """Halt once total tokens exceed ``limit`` (a stand-in for a cost cap)."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.name = f"token_budget({limit})"

    def check(self, state: KernelState) -> StopDecision | None:
        total = state.tokens_in + state.tokens_out
        if total >= self.limit:
            return StopDecision(
                status=RunStatus.BUDGET_EXCEEDED,
                reason=f"token budget {self.limit} exceeded ({total})",
                policy=self.name,
            )
        return None


class AnyOf:
    """Combine policies with OR semantics: the first that halts wins."""

    def __init__(self, *policies: StopPolicy) -> None:
        self.policies = policies
        self.name = "any_of"

    def check(self, state: KernelState) -> StopDecision | None:
        for policy in self.policies:
            decision = policy.check(state)
            if decision is not None:
                return decision
        return None


class NoProgress:
    """Halt when the last ``window`` actions share one signature.

    This is *no-progress detection*: the agent keeps calling the same tool with
    the same args and learning nothing. Left alone it burns the whole budget
    oscillating. M1 stops the run (``stalled``); M2 will intervene instead of
    giving up (anti-thrash) using the very same signature stream.
    """

    def __init__(self, window: int = 3) -> None:
        self.window = window
        self.name = f"no_progress({window})"

    def check(self, state: KernelState) -> StopDecision | None:
        sigs = state.action_signatures
        if len(sigs) >= self.window and len(set(sigs[-self.window :])) == 1:
            return StopDecision(
                status=RunStatus.STALLED,
                reason=f"same action repeated {self.window}× with no progress: {sigs[-1]}",
                policy=self.name,
            )
        return None
