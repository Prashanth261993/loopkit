"""sinks.py — where events go.

A :class:`Sink` is anything that can ``handle`` an event. The kernel is
sink-agnostic, so the same run can fan out to a file, an in-memory list (tests),
and later a live WebSocket (the dashboard) at once.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol, runtime_checkable

from loopkit.events import Event


@runtime_checkable
class Sink(Protocol):
    def handle(self, event: Event) -> None: ...


class JsonlSink:
    """Append each event as one JSON line. This is the deterministic record
    that replay, CI and the eval harness all consume."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._f = self.path.open("w", encoding="utf-8")

    def handle(self, event: Event) -> None:
        self._f.write(event.model_dump_json() + "\n")
        self._f.flush()

    def close(self) -> None:
        self._f.close()

    def __enter__(self) -> "JsonlSink":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class MemorySink:
    """Collect events in a list. Handy for assertions in tests."""

    def __init__(self) -> None:
        self.events: list[Event] = []

    def handle(self, event: Event) -> None:
        self.events.append(event)

    def of_type(self, type_value: str) -> list[Event]:
        return [e for e in self.events if e.type.value == type_value]


def read_jsonl(path: str | Path) -> list[Event]:
    """Load a recorded run back into :class:`Event` objects (replay)."""
    events: list[Event] = []
    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(Event.model_validate(json.loads(line)))
    return events
