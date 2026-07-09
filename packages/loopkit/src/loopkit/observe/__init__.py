"""observe — the live/replay transport for the event stream (M3).

The kernel already emits a versioned :class:`~loopkit.events.Event` stream to any
:class:`~loopkit.sinks.Sink`. M3 adds a *second consumer shape* on top of the
same stream without touching the kernel:

  * :class:`SseSink` — fans live events to any number of browser clients over
    Server-Sent Events.
  * :func:`serve` — a zero-dependency (stdlib only) HTTP server that serves the
    built dashboard, lists recorded runs, replays a ``.jsonl`` artifact over SSE
    with pacing, and exposes the live feed.

The dashboard reads the *identical* event objects whether they arrive from a
dropped ``.jsonl`` file (static, no backend — the M6 showcase path) or from this
server's SSE endpoints. One schema, two transports.
"""

from __future__ import annotations

from loopkit.observe.sse import BroadcastHub, SseSink
from loopkit.observe.server import serve

__all__ = ["SseSink", "BroadcastHub", "serve"]
