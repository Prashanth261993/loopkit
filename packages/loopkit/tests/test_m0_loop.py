"""M0 tests — the whole runtime is exercised with zero LLM via MockAdapter."""

from __future__ import annotations

from loopkit import EventBus, Kernel, ToolRegistry
from loopkit.adapters import MockAdapter, act, final
from loopkit.policies import AnyOf, MaxIterations, TokenBudget
from loopkit.sinks import MemorySink
from loopkit.tools import Tool


def _registry(allow_writes=None) -> ToolRegistry:
    reg = ToolRegistry(allow_writes=allow_writes or [])

    @reg.tool("reverse", "Reverse a string")
    def reverse(args):
        return args["text"][::-1]

    reg.register(
        Tool(
            name="write_file",
            description="write (destructive)",
            handler=lambda a: "WROTE",
            destructive=True,
        )
    )
    return reg


def _run(script, allow_writes=None, stop=None):
    mem = MemorySink()
    bus = EventBus(run_id="test", sinks=[mem])
    kernel = Kernel(
        adapter=MockAdapter(script),
        registry=_registry(allow_writes),
        stop_policy=stop or AnyOf(MaxIterations(10), TokenBudget(10_000)),
        bus=bus,
    )
    result = kernel.run("do the thing")
    return result, mem


def test_stream_opens_and_closes_correctly():
    result, mem = _run([act("reverse", {"text": "abc"}), final("cba")])
    types = [e.type.value for e in mem.events]
    assert types[0] == "run.start"
    assert types[-1] == "run.end"
    assert result.status == "success"
    assert result.result == "cba"


def test_seq_is_dense_and_ordered():
    _, mem = _run([final("done")])
    seqs = [e.seq for e in mem.events]
    assert seqs == list(range(len(seqs)))


def test_destructive_tool_is_dry_run_without_allowlist():
    _, mem = _run([act("write_file", {"path": "x"}), final("ok")])
    tr = next(e for e in mem.of_type("tool.result") if e.data["name"] == "write_file")
    assert tr.data["dry_run"] is True


def test_destructive_tool_runs_when_allowlisted():
    _, mem = _run(
        [act("write_file", {"path": "x"}), final("ok")], allow_writes=["write_file"]
    )
    tr = next(e for e in mem.of_type("tool.result") if e.data["name"] == "write_file")
    assert tr.data["dry_run"] is False
    assert tr.data["output"] == "WROTE"


def test_unknown_tool_reports_error():
    _, mem = _run([act("nope", {}), final("ok")])
    tr = mem.of_type("tool.result")[0]
    assert tr.data["ok"] is False
    assert "unknown tool" in tr.data["error"]


def test_max_iterations_stops_involuntarily():
    # Never emits a final -> the stop policy must terminate the run.
    script = [act("reverse", {"text": "a"}) for _ in range(5)]
    result, mem = _run(script, stop=MaxIterations(3))
    assert result.status == "max_iters"
    assert result.iterations == 3
    stop = mem.of_type("stop.check")[-1]
    assert "max_iterations" in stop.data["policy"]


def test_run_start_records_safety_config():
    _, mem = _run([final("done")])
    start = mem.of_type("run.start")[0]
    assert start.data["safety"]["mode"] == "dry_run_by_default"
    assert "write_file" in start.data["safety"]["destructive_tools"]
