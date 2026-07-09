"""events.py — the versioned event schema. This is LoopKit's public API seam.

Every meaningful thing the kernel does is emitted as an :class:`Event` with a
stable envelope (``schema_version, run_id, seq, ts, iteration, type``) and a
free-form ``data`` payload. Two consumers read the SAME stream:

  * a JSONL file  -> deterministic replay, CI, evals
  * a live sink   -> the dashboard (added in M3)

Because the envelope is versioned, the Python kernel and the TypeScript
dashboard can evolve independently as long as they agree on this schema.
"""

from __future__ import annotations

import itertools
import time
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

SCHEMA_VERSION = "0.1.0"


class EventType(str, Enum):
    """The 12 event types that describe a full agent run."""

    RUN_START = "run.start"
    ITERATION_START = "iteration.start"
    MODEL_REQUEST = "model.request"
    MODEL_RESPONSE = "model.response"
    TOOL_CALL = "tool.call"
    TOOL_RESULT = "tool.result"
    HEAL_TRIGGER = "heal.trigger"        # emitted from M2
    HEAL_CRITIQUE = "heal.critique"      # emitted from M2
    HEAL_RETRY = "heal.retry"            # emitted from M2
    THRASH_DETECTED = "thrash.detected"  # emitted from M2
    STOP_CHECK = "stop.check"
    RUN_END = "run.end"


class RunStatus(str, Enum):
    """Terminal status of a run, carried on ``run.end``."""

    SUCCESS = "success"
    FAILED = "failed"
    MAX_ITERS = "max_iters"
    BUDGET_EXCEEDED = "budget_exceeded"
    STALLED = "stalled"
    RUNNING = "running"  # transient, never on run.end


class Event(BaseModel):
    """A single point on the timeline.

    The envelope fields are fixed across all event types; ``type`` discriminates
    and ``data`` carries the type-specific payload. Keeping ``data`` open in v0.1
    lets us add fields without a schema bump; payloads tighten in later versions.
    """

    schema_version: str = SCHEMA_VERSION
    run_id: str
    seq: int
    ts: float = Field(default_factory=time.time)
    iteration: int
    type: EventType
    data: dict[str, Any] = Field(default_factory=dict)


class EventBus:
    """Owns the monotonic ``seq`` counter and fans events out to sinks.

    The kernel never constructs an :class:`Event` directly; it calls
    :meth:`emit`, which stamps the envelope. That guarantees ``seq`` is dense and
    ordered — the property replay and evals rely on.
    """

    def __init__(self, run_id: str, sinks: list["Sink"]) -> None:
        self.run_id = run_id
        self.sinks = sinks
        self.iteration = 0
        self._seq = itertools.count()

    def emit(self, type: EventType, **data: Any) -> Event:
        event = Event(
            run_id=self.run_id,
            seq=next(self._seq),
            iteration=self.iteration,
            type=type,
            data=data,
        )
        for sink in self.sinks:
            sink.handle(event)
        return event


# Imported lazily for the type hint above without creating a cycle at runtime.
from loopkit.sinks import Sink  # noqa: E402
