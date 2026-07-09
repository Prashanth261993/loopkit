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
    action_signatures: list[str] = field(default_factory=list)
    status: str = "running"
    result: str | None = None


def action_signature(name: str, args: dict[str, Any]) -> str:
    """Stable fingerprint of a tool call, order-insensitive on args.

    Used by no-progress detection (M1) and anti-thrash (M2): if the agent keeps
    producing the *same* signature, it's stuck in a loop and getting nowhere.
    """
    try:
        items = sorted((str(k), repr(v)) for k, v in args.items())
    except Exception:
        items = [repr(args)]
    return f"{name}({','.join(f'{k}={v}' for k, v in items)})"
