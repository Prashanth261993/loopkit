"""state.py — the read-only view of a run that policies inspect.

Kept separate from the kernel so that stop/context/heal policies can depend on
the *state shape* without importing the kernel (no cycles, easy to test).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class KernelState:
    run_id: str
    task: str
    iteration: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost: float = 0.0
    history: list[dict[str, Any]] = field(default_factory=list)
    last_action: tuple[str, dict[str, Any]] | None = None
    status: str = "running"
    result: str | None = None
