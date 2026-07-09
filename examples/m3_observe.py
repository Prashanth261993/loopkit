"""m3_observe.py — the M3 observability layer, proven with ZERO LLM.

M0 made the loop run, M1 made it survivable, M2 made it self-correcting. M3 makes
it *visible*. The kernel already emits a versioned event stream; M3 adds a second
consumer shape on top of the same stream:

  * a **JSONL artifact** (deterministic record — replay, CI, evals), and
  * a **live SSE feed** (the dashboard watches a run as it happens).

The dashboard reads the *identical* event objects whether they were replayed from
a dropped ``.jsonl`` file (static, no backend — the showcase path) or streamed
live from the server. One schema, two transports.

This script scripts a realistic "release-readiness" agent so the recorded run is
worth watching: a tool errors once and the loop heals it, several tools run, and
the agent gives a clean final answer. It writes the artifact to
``artifacts/m3_observe.jsonl`` AND copies it to ``dashboard/public/sample.jsonl``
so the built dashboard shows a real self-healing run with zero setup.

Run it:
    python examples/m3_observe.py            # record the artifact + copy sample
    python examples/m3_observe.py --serve    # ...then serve the live dashboard
"""

from __future__ import annotations

import shutil
import sys
import threading
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from loopkit import (
    AnyOf,
    EventBus,
    HealPolicy,
    Kernel,
    MaxIterations,
    ReflexionMemory,
    RuleBasedCritic,
    ToolRegistry,
)
from loopkit.adapters import MockAdapter, act, final
from loopkit.observe import BroadcastHub, SseSink, serve
from loopkit.sinks import JsonlSink

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = REPO_ROOT / "artifacts" / "m3_observe.jsonl"
SAMPLE = REPO_ROOT / "dashboard" / "public" / "sample.jsonl"
DIST = REPO_ROOT / "dashboard" / "dist"


def build_release_agent(bus: EventBus) -> Kernel:
    """A release-readiness agent whose test suite is flaky on the first run.

    The first ``run_tests`` call raises (a transient CI hiccup). The RuleBasedCritic
    files a ``tool_error`` critique, a Reflexion note is injected, and the bounded
    retry passes — then the agent reads the changelog, lints, and signs off.
    """
    registry = ToolRegistry(allow_writes=[])
    state = {"test_runs": 0}

    @registry.tool("run_tests", "Run the unit test suite", schema={"suite": "str"})
    def run_tests(args: dict) -> str:
        state["test_runs"] += 1
        if state["test_runs"] == 1:
            raise RuntimeError("pytest: connection to test DB timed out (transient)")
        return "42 passed in 3.1s"

    @registry.tool("read_file", "Read a file from the repo", schema={"path": "str"})
    def read_file(args: dict) -> str:
        return "## 0.3.0\n- add observe layer\n- self-heal on tool_error"

    @registry.tool("lint", "Run the linter", schema={"paths": "list"})
    def lint(args: dict) -> str:
        return "ruff: all checks passed"

    # Scripted turns. Note the doubled run_tests: the first errors and is healed,
    # the retry (a fresh iteration) pulls the second run_tests and succeeds.
    script = [
        act("run_tests", {"suite": "unit"}, thought="Start by proving the suite is green."),
        act("run_tests", {"suite": "unit"}, thought="Transient failure — retry the suite."),
        act("read_file", {"path": "CHANGELOG.md"}, thought="Confirm the changelog is updated."),
        act("lint", {"paths": ["src"]}, thought="Final gate: lint must be clean."),
        final(
            "Release 0.3.0 is ready: unit tests green (healed one transient failure), "
            "CHANGELOG updated, lint clean."
        ),
    ]

    return Kernel(
        adapter=MockAdapter(script),
        registry=registry,
        stop_policy=AnyOf(MaxIterations(50)),
        bus=bus,
        critic=RuleBasedCritic(),
        heal_policy=HealPolicy(max_heals=3),
        reflexion=ReflexionMemory(),
    )


def record() -> None:
    """Run the agent once, writing the JSONL artifact and copying the sample."""
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    SAMPLE.parent.mkdir(parents=True, exist_ok=True)

    sink = JsonlSink(ARTIFACT)
    bus = EventBus(run_id="m3-release-readiness", sinks=[sink])
    kernel = build_release_agent(bus)
    result = kernel.run("Decide whether release 0.3.0 is ready to ship.")
    sink.close()

    shutil.copyfile(ARTIFACT, SAMPLE)

    print("=" * 64)
    print("LoopKit M3 — OBSERVE, recorded with a scripted (zero-LLM) model")
    print("=" * 64)
    print(f"  status        : {result.status}")
    print(f"  iterations    : {result.iterations}")
    print(f"  heals         : {result.heals}")
    print(f"  tokens        : {result.tokens_in} in / {result.tokens_out} out")
    print(f"  artifact      : {ARTIFACT.relative_to(REPO_ROOT)}")
    print(f"  dashboard fix : {SAMPLE.relative_to(REPO_ROOT)}")
    assert result.status == "success", result.status
    assert result.heals == 1, result.heals
    print("  OK ✅  self-healing run recorded and copied for the dashboard")


def serve_live(port: int = 8765) -> None:
    """Record to the artifact live over SSE, then serve the built dashboard.

    Open http://127.0.0.1:8765 and either drop the sample .jsonl, connect to the
    live ``/events`` feed, or replay a recorded run from ``/api/runs``.
    """
    if not DIST.is_dir():
        print("dashboard not built — run `npm install && npm run build` in dashboard/")
        return

    hub = BroadcastHub()
    httpd = serve(artifacts_dir=ARTIFACT.parent, dist_dir=DIST, hub=hub, port=port)
    print("=" * 64)
    print(f"  LoopKit observe server → http://127.0.0.1:{port}")
    print("  routes: /  /api/runs  /api/replay?run=NAME  /events")
    print("  Ctrl+C to stop.")
    print("=" * 64)

    def run_agent() -> None:
        # Give a browser a moment to connect to /events before the (fast) run.
        threading.Event().wait(1.5)
        bus = EventBus(run_id="m3-live", sinks=[JsonlSink(ARTIFACT), SseSink(hub)])
        build_release_agent(bus).run("Decide whether release 0.3.0 is ready to ship.")
        hub.close()

    threading.Thread(target=run_agent, daemon=True).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  server stopped.")
    finally:
        httpd.shutdown()


def main() -> None:
    record()
    if "--serve" in sys.argv:
        serve_live()


if __name__ == "__main__":
    main()
