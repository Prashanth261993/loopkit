"""SSE fan-out: a broadcast hub + a Sink that publishes to it.

``SseSink`` is a normal :class:`~loopkit.sinks.Sink` — you add it to the
``EventBus`` alongside (or instead of) a ``JsonlSink``. Every event it receives
is serialized with the *same* ``model_dump_json()`` used for the on-disk record
and pushed to every currently-connected browser. Because the wire format is
identical to the JSONL record, the dashboard cannot tell (and does not care)
whether an event was replayed from a file or streamed live.

The hub is deliberately tiny and thread-safe: the kernel runs on one thread and
each SSE client is served on its own thread by ``ThreadingHTTPServer``.
"""

from __future__ import annotations

import queue
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from loopkit.events import Event


class BroadcastHub:
    """Fan-out of serialized event lines to N subscriber queues.

    Each subscriber (one per connected SSE client) gets its own bounded queue.
    Publishing is non-blocking: if a slow client's queue is full we drop the
    oldest item rather than stalling the kernel — observability must never back-
    pressure the loop it observes.
    """

    def __init__(self, *, max_queue: int = 1000) -> None:
        self._subscribers: set[queue.Queue[str | None]] = set()
        self._lock = threading.Lock()
        self._max_queue = max_queue

    def subscribe(self) -> queue.Queue[str | None]:
        q: queue.Queue[str | None] = queue.Queue(maxsize=self._max_queue)
        with self._lock:
            self._subscribers.add(q)
        return q

    def unsubscribe(self, q: queue.Queue[str | None]) -> None:
        with self._lock:
            self._subscribers.discard(q)

    def publish(self, line: str) -> None:
        with self._lock:
            subs = list(self._subscribers)
        for q in subs:
            _offer(q, line)

    def close(self) -> None:
        """Signal all subscribers to end their streams (sentinel ``None``)."""
        with self._lock:
            subs = list(self._subscribers)
        for q in subs:
            _offer(q, None)

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)


def _offer(q: queue.Queue[str | None], item: str | None) -> None:
    """Put ``item`` on ``q``, dropping the oldest entry if the queue is full."""
    try:
        q.put_nowait(item)
    except queue.Full:
        try:
            q.get_nowait()
        except queue.Empty:
            pass
        try:
            q.put_nowait(item)
        except queue.Full:  # pragma: no cover - extremely unlikely
            pass


class SseSink:
    """A :class:`~loopkit.sinks.Sink` that broadcasts events to a hub."""

    def __init__(self, hub: BroadcastHub) -> None:
        self.hub = hub

    def handle(self, event: "Event") -> None:
        self.hub.publish(event.model_dump_json())
