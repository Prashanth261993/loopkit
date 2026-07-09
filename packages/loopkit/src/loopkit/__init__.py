"""LoopKit — a framework-agnostic agent-loop kernel.

The model is a commodity; the loop around it is the engineering. LoopKit gives
you that loop — with observability, safety, and (from M2) self-healing — behind
small pluggable interfaces.

Quick start::

    from loopkit import Kernel, EventBus, ToolRegistry, Tool
    from loopkit.adapters import MockAdapter, act, final
    from loopkit.policies import AnyOf, MaxIterations
    from loopkit.sinks import JsonlSink

See ``examples/m0_zero_llm.py`` for a full zero-LLM run.
"""

from loopkit.events import Event, EventBus, EventType, RunStatus, SCHEMA_VERSION
from loopkit.kernel import Kernel, LoopResult
from loopkit.state import KernelState
from loopkit.tools import Tool, ToolRegistry, ToolResult

__version__ = "0.1.0"

__all__ = [
    "Kernel",
    "LoopResult",
    "KernelState",
    "EventBus",
    "Event",
    "EventType",
    "RunStatus",
    "SCHEMA_VERSION",
    "Tool",
    "ToolRegistry",
    "ToolResult",
    "__version__",
]
