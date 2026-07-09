"""test_m3_observe.py — the M3 observability transport.

Three layers, all deterministic and offline:
  * BroadcastHub — subscribe/publish/unsubscribe fan-out, the drop-oldest policy
    that guarantees observability never back-pressures the loop, and the close
    sentinel.
  * SseSink — a real :class:`Sink`; wiring it into an EventBus must serialize each
    event with the exact same ``model_dump_json`` the JSONL record uses.
  * serve() — the stdlib HTTP server: run listing, replay-over-SSE, path-traversal
    protection, and static/SPA fallback, exercised against a real bound socket.

M0/M1/M2 stay green — observe is additive and touches nothing in the kernel.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

from loopkit import AnyOf, EventBus, Kernel, MaxIterations, ToolRegistry
from loopkit.adapters import MockAdapter, act, final
from loopkit.events import Event, EventType
from loopkit.observe import BroadcastHub, SseSink, serve
from loopkit.observe.server import _clamp_speed, _iter_jsonl_ts


# --------------------------------------------------------------------------- #
# BroadcastHub
# --------------------------------------------------------------------------- #
def test_hub_fans_out_to_all_subscribers() -> None:
    hub = BroadcastHub()
    a = hub.subscribe()
    b = hub.subscribe()
    assert hub.subscriber_count == 2

    hub.publish("hello")
    assert a.get_nowait() == "hello"
    assert b.get_nowait() == "hello"


def test_hub_unsubscribe_stops_delivery() -> None:
    hub = BroadcastHub()
    a = hub.subscribe()
    hub.unsubscribe(a)
    assert hub.subscriber_count == 0
    hub.publish("after")
    assert a.empty()


def test_hub_drops_oldest_when_full() -> None:
    # A slow client must never stall the kernel: when its queue is full the hub
    # evicts the oldest line and keeps the newest rather than blocking.
    hub = BroadcastHub(max_queue=2)
    q = hub.subscribe()
    hub.publish("1")
    hub.publish("2")
    hub.publish("3")  # evicts "1"

    drained = [q.get_nowait(), q.get_nowait()]
    assert drained == ["2", "3"]
    assert q.empty()


def test_hub_close_sends_sentinel() -> None:
    hub = BroadcastHub()
    q = hub.subscribe()
    hub.close()
    assert q.get_nowait() is None


# --------------------------------------------------------------------------- #
# SseSink
# --------------------------------------------------------------------------- #
def _event(seq: int, type_: EventType, **data: object) -> Event:
    return Event(run_id="t", seq=seq, iteration=0, type=type_, data=data)


def test_sse_sink_publishes_exact_json_line() -> None:
    hub = BroadcastHub()
    q = hub.subscribe()
    sink = SseSink(hub)

    ev = _event(0, EventType.RUN_START, task="demo")
    sink.handle(ev)

    line = q.get_nowait()
    # The wire format must be byte-identical to the on-disk JSONL record so the
    # dashboard cannot tell live from replay.
    assert line == ev.model_dump_json()
    assert json.loads(line)["data"]["task"] == "demo"


def test_sse_sink_streams_a_full_run(tmp_path: Path) -> None:
    # SseSink is a normal Sink: an EventBus with it wired in fans a real run out.
    hub = BroadcastHub()
    q = hub.subscribe()

    registry = ToolRegistry(allow_writes=[])

    @registry.tool("noop", "no-op", schema={})
    def noop(args: dict) -> str:
        return "ok"

    bus = EventBus(run_id="sse-run", sinks=[SseSink(hub)])
    kernel = Kernel(
        adapter=MockAdapter([act("noop", {}), final("done")]),
        registry=registry,
        stop_policy=AnyOf(MaxIterations(10)),
        bus=bus,
    )
    kernel.run("do the thing")

    types = []
    while not q.empty():
        types.append(json.loads(q.get_nowait())["type"])
    assert types[0] == "run.start"
    assert types[-1] == "run.end"
    assert "tool.call" in types


# --------------------------------------------------------------------------- #
# server helpers
# --------------------------------------------------------------------------- #
def test_clamp_speed_bounds_and_fallback() -> None:
    assert _clamp_speed("1") == 1.0
    assert _clamp_speed("0") == 0.1  # floor
    assert _clamp_speed("999") == 50.0  # ceiling
    assert _clamp_speed("not-a-number") == 1.0  # fallback


def test_iter_jsonl_ts_skips_blank_and_reads_ts(tmp_path: Path) -> None:
    art = tmp_path / "run.jsonl"
    art.write_text(
        '{"ts": 1.0, "type": "run.start"}\n\n{"ts": 2.5, "type": "run.end"}\n',
        encoding="utf-8",
    )
    rows = list(_iter_jsonl_ts(art))
    assert [ts for ts, _ in rows] == [1.0, 2.5]


# --------------------------------------------------------------------------- #
# serve() — real socket integration
# --------------------------------------------------------------------------- #
def _boot(tmp_path: Path) -> tuple[str, object]:
    artifacts = tmp_path / "artifacts"
    dist = tmp_path / "dist"
    artifacts.mkdir()
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>ok</title>", encoding="utf-8")
    (artifacts / "demo.jsonl").write_text(
        '{"ts": 0.0, "seq": 0, "type": "run.start"}\n'
        '{"ts": 0.01, "seq": 1, "type": "run.end"}\n',
        encoding="utf-8",
    )
    httpd = serve(artifacts_dir=artifacts, dist_dir=dist, host="127.0.0.1", port=0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.server_address[1]
    return f"http://127.0.0.1:{port}", httpd


def _get(url: str) -> tuple[int, str]:
    with urllib.request.urlopen(url, timeout=5) as resp:  # noqa: S310 - localhost test
        return resp.status, resp.read().decode("utf-8")


def test_server_lists_runs(tmp_path: Path) -> None:
    base, httpd = _boot(tmp_path)
    try:
        status, body = _get(f"{base}/api/runs")
        assert status == 200
        payload = json.loads(body)
        assert [r["name"] for r in payload["runs"]] == ["demo.jsonl"]
        assert payload["runs"][0]["bytes"] > 0
    finally:
        httpd.shutdown()


def _read_sse(url: str) -> str:
    # SSE responses stay open (keep-alive), so read incrementally and stop once
    # the terminal `event: end` frame arrives rather than blocking to EOF.
    with urllib.request.urlopen(url, timeout=5) as resp:  # noqa: S310 - localhost test
        chunks = []
        while True:
            line = resp.fp.readline()
            if not line:
                break
            chunks.append(line.decode("utf-8"))
            if line.startswith(b"event: end"):
                break
        return "".join(chunks)


def test_server_replays_artifact_over_sse(tmp_path: Path) -> None:
    base, httpd = _boot(tmp_path)
    try:
        body = _read_sse(f"{base}/api/replay?run=demo.jsonl&speed=50")
        assert "run.start" in body
        assert "run.end" in body
        assert "event: end" in body  # terminal frame
    finally:
        httpd.shutdown()


def test_server_blocks_path_traversal(tmp_path: Path) -> None:
    base, httpd = _boot(tmp_path)
    try:
        # A traversal attempt must not escape the artifacts dir.
        status_code = 0
        try:
            _get(f"{base}/api/replay?run=..%2f..%2fsecret.jsonl")
        except urllib.error.HTTPError as exc:  # type: ignore[attr-defined]
            status_code = exc.code
        assert status_code == 404
    finally:
        httpd.shutdown()


def test_server_spa_fallback_serves_index(tmp_path: Path) -> None:
    base, httpd = _boot(tmp_path)
    try:
        # An unknown client route falls back to index.html (single-page app).
        status, body = _get(f"{base}/some/deep/route")
        assert status == 200
        assert "<title>ok</title>" in body
    finally:
        httpd.shutdown()
