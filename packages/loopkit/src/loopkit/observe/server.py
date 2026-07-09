"""A zero-dependency HTTP server for the dashboard (stdlib only).

Deliberately built on ``http.server`` — no Flask/FastAPI, no new runtime
dependency added to ``pip install loopkit``. It does four things:

* ``GET /``, ``GET /<asset>``  — serve the built dashboard from ``dist_dir``.
* ``GET /api/runs``            — JSON list of ``*.jsonl`` artifacts.
* ``GET /api/replay?run=NAME`` — stream that artifact over SSE, paced by the
  recorded ``ts`` deltas (scaled by ``?speed=``) so a replay *feels* like a live
  run. This is the endpoint the "connect to server" demo uses.
* ``GET /events``             — the live feed: subscribe to a :class:`BroadcastHub`
  and forward every event an :class:`SseSink` publishes.

Routes are matched before any filesystem lookup, and static paths are resolved
under ``dist_dir`` with traversal protection.
"""

from __future__ import annotations

import json
import mimetypes
import queue
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from loopkit.observe.sse import BroadcastHub

# Pacing bounds for replay (seconds of wall-clock between emitted events).
_REPLAY_MIN_DELAY = 0.02
_REPLAY_MAX_DELAY = 0.75


def _sse_frame(line: str) -> bytes:
    return f"data: {line}\n\n".encode("utf-8")


def _iter_jsonl_ts(path: Path):
    """Yield ``(timestamp, raw_line)`` for each event line in an artifact."""
    with path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                ts = float(json.loads(raw).get("ts", 0.0))
            except (ValueError, TypeError):
                ts = 0.0
            yield ts, raw


class _Handler(BaseHTTPRequestHandler):
    # Injected on the server instance by ``serve``.
    artifacts_dir: Path
    dist_dir: Path
    hub: BroadcastHub

    server_version = "LoopKitObserve/0.1"

    def log_message(self, *args) -> None:  # noqa: D401 - silence default logging
        """Silence per-request stderr logging (the demo prints its own banner)."""

    # --- routing -----------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        parsed = urlparse(self.path)
        route = parsed.path
        params = parse_qs(parsed.query)

        if route == "/api/runs":
            self._send_runs()
        elif route == "/api/replay":
            self._send_replay(params)
        elif route == "/events":
            self._send_live()
        else:
            self._send_static(route)

    # --- JSON: list runs ---------------------------------------------------
    def _send_runs(self) -> None:
        runs = []
        if self.artifacts_dir.is_dir():
            for p in sorted(self.artifacts_dir.glob("*.jsonl")):
                runs.append({"name": p.name, "bytes": p.stat().st_size})
        body = json.dumps({"runs": runs}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    # --- SSE: replay a recorded artifact -----------------------------------
    def _send_replay(self, params: dict[str, list[str]]) -> None:
        name = (params.get("run") or [""])[0]
        speed = _clamp_speed((params.get("speed") or ["1"])[0])
        path = self._safe_artifact(name)
        if path is None:
            self.send_error(404, "run not found")
            return
        if not self._begin_sse():
            return
        prev_ts: float | None = None
        try:
            for ts, raw in _iter_jsonl_ts(path):
                if prev_ts is not None:
                    delay = (ts - prev_ts) / speed
                    delay = max(_REPLAY_MIN_DELAY, min(_REPLAY_MAX_DELAY, delay))
                    time.sleep(delay)
                prev_ts = ts
                self.wfile.write(_sse_frame(raw))
                self.wfile.flush()
            self.wfile.write(b"event: end\ndata: {}\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

    # --- SSE: live feed from the hub ---------------------------------------
    def _send_live(self) -> None:
        if not self._begin_sse():
            return
        q = self.hub.subscribe()
        try:
            # Prime the connection so browsers fire `onopen` promptly.
            self.wfile.write(b": connected\n\n")
            self.wfile.flush()
            while True:
                try:
                    line = q.get(timeout=15.0)
                except queue.Empty:
                    self.wfile.write(b": keep-alive\n\n")  # heartbeat
                    self.wfile.flush()
                    continue
                if line is None:  # hub closed
                    self.wfile.write(b"event: end\ndata: {}\n\n")
                    self.wfile.flush()
                    break
                self.wfile.write(_sse_frame(line))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            self.hub.unsubscribe(q)

    # --- static files ------------------------------------------------------
    def _send_static(self, route: str) -> None:
        rel = route.lstrip("/") or "index.html"
        target = (self.dist_dir / rel).resolve()
        try:
            target.relative_to(self.dist_dir.resolve())
        except ValueError:
            self.send_error(403, "forbidden")
            return
        if not target.is_file():
            # SPA fallback: unknown routes serve index.html.
            target = self.dist_dir / "index.html"
        if not target.is_file():
            self.send_error(
                404,
                "dashboard not built — run `npm install && npm run build` in dashboard/",
            )
            return
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # --- helpers -----------------------------------------------------------
    def _begin_sse(self) -> bool:
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            return True
        except (BrokenPipeError, ConnectionResetError):
            return False

    def _safe_artifact(self, name: str) -> Path | None:
        if not name or "/" in name or "\\" in name or not name.endswith(".jsonl"):
            return None
        candidate = (self.artifacts_dir / name).resolve()
        try:
            candidate.relative_to(self.artifacts_dir.resolve())
        except ValueError:
            return None
        return candidate if candidate.is_file() else None


def _clamp_speed(raw: str) -> float:
    try:
        speed = float(raw)
    except (ValueError, TypeError):
        return 1.0
    return max(0.1, min(50.0, speed))


def serve(
    *,
    artifacts_dir: str | Path = "artifacts",
    dist_dir: str | Path | None = None,
    hub: BroadcastHub | None = None,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> ThreadingHTTPServer:
    """Build (but do not block on) the observe server.

    Returns a started ``ThreadingHTTPServer`` — call ``.serve_forever()`` to
    block, or drive it from a background thread. ``hub`` is optional; pass the
    same hub an :class:`SseSink` publishes to in order to enable the ``/events``
    live feed.
    """
    artifacts = Path(artifacts_dir)
    dist = Path(dist_dir) if dist_dir is not None else _default_dist()

    handler = _Handler
    httpd = ThreadingHTTPServer((host, port), handler)
    # Attach config to the handler class via the server (handlers read class attrs).
    handler.artifacts_dir = artifacts
    handler.dist_dir = dist
    handler.hub = hub if hub is not None else BroadcastHub()
    return httpd


def _default_dist() -> Path:
    """Locate ``dashboard/dist`` relative to the repo root, best-effort."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "dashboard" / "dist"
        if candidate.exists():
            return candidate
    return Path("dashboard/dist")
