"""governor.py — the always-on resource rail.

A :class:`StopPolicy` answers *"is the task done?"* (goal, no-progress). A
:class:`Governor` answers a different question: *"have we spent too much?"* —
tokens, dollars, iterations, wall-clock. It's the seatbelt that stops a
runaway loop from burning your budget while you're asleep.

Separating the two matters at staff level: termination is task logic and lives
with the agent author; resource caps are an operational guardrail the platform
enforces regardless of what the agent thinks it's doing. The kernel charges the
governor every turn and honours its verdict *before* the next model call.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from loopkit.events import RunStatus


@dataclass
class CostModel:
    """Price per 1K tokens. Defaults to free (local/Ollama story)."""

    per_1k_in: float = 0.0
    per_1k_out: float = 0.0

    def cost(self, tokens_in: int, tokens_out: int) -> float:
        return tokens_in / 1000 * self.per_1k_in + tokens_out / 1000 * self.per_1k_out


@dataclass
class GovernorDecision:
    status: RunStatus
    reason: str
    policy: str = "governor"


class Governor:
    """Accumulates usage and trips when any configured cap is crossed.

    Every cap is optional; omit one to leave it uncapped. ``check`` returns a
    :class:`GovernorDecision` the *first* time a cap is exceeded, otherwise
    ``None``. It reports :data:`RunStatus.BUDGET_EXCEEDED` for token/cost/wall
    caps and :data:`RunStatus.MAX_ITERS` for the iteration cap, so a viewer can
    tell *why* the seatbelt engaged.
    """

    def __init__(
        self,
        *,
        max_tokens: int | None = None,
        max_cost: float | None = None,
        max_iterations: int | None = None,
        max_wall_seconds: float | None = None,
        cost_model: CostModel | None = None,
    ) -> None:
        self.max_tokens = max_tokens
        self.max_cost = max_cost
        self.max_iterations = max_iterations
        self.max_wall_seconds = max_wall_seconds
        self.cost_model = cost_model or CostModel()

        self.tokens_in = 0
        self.tokens_out = 0
        self.cost = 0.0
        self.iterations = 0
        self._start = time.monotonic()

    def charge(self, *, tokens_in: int, tokens_out: int, iteration: int) -> float:
        """Record one turn's spend. Returns the *incremental* cost so the kernel
        can stamp it onto ``model.response``."""
        self.tokens_in += tokens_in
        self.tokens_out += tokens_out
        self.iterations = iteration
        delta = self.cost_model.cost(tokens_in, tokens_out)
        self.cost += delta
        return delta

    @property
    def tokens(self) -> int:
        return self.tokens_in + self.tokens_out

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self._start

    def check(self) -> GovernorDecision | None:
        if self.max_tokens is not None and self.tokens >= self.max_tokens:
            return GovernorDecision(
                RunStatus.BUDGET_EXCEEDED,
                f"token cap reached: {self.tokens} >= {self.max_tokens}",
            )
        if self.max_cost is not None and self.cost >= self.max_cost:
            return GovernorDecision(
                RunStatus.BUDGET_EXCEEDED,
                f"cost cap reached: {self.cost:.4f} >= {self.max_cost}",
            )
        if self.max_wall_seconds is not None and self.elapsed >= self.max_wall_seconds:
            return GovernorDecision(
                RunStatus.BUDGET_EXCEEDED,
                f"wall-clock cap reached: {self.elapsed:.1f}s >= {self.max_wall_seconds}s",
            )
        if self.max_iterations is not None and self.iterations >= self.max_iterations:
            return GovernorDecision(
                RunStatus.MAX_ITERS,
                f"iteration cap reached: {self.iterations} >= {self.max_iterations}",
            )
        return None

    def snapshot(self) -> dict:
        """Caps recorded into ``run.start`` so a run is self-describing."""
        return {
            "max_tokens": self.max_tokens,
            "max_cost": self.max_cost,
            "max_iterations": self.max_iterations,
            "max_wall_seconds": self.max_wall_seconds,
            "cost_model": {
                "per_1k_in": self.cost_model.per_1k_in,
                "per_1k_out": self.cost_model.per_1k_out,
            },
        }

    def usage(self) -> dict:
        """Totals recorded onto ``run.end``."""
        return {
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "tokens": self.tokens,
            "cost": round(self.cost, 6),
            "iterations": self.iterations,
            "elapsed": round(self.elapsed, 3),
        }


__all__ = ["Governor", "GovernorDecision", "CostModel"]
