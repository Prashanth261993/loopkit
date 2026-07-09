"""m1_runtime.py — the M1 runtime features, proven with ZERO LLM.

M0 proved the loop runs. M1 makes it *survivable* for long, real runs. This
example exercises the three new rails, each with the deterministic MockAdapter so
it's hermetic and CI-safe:

  1. Context compaction  — history is windowed + summarized; the model stops
                           seeing the whole ever-growing transcript.
  2. Governor            — a hard token cap trips the run to `budget_exceeded`
                           regardless of what the agent wants to do next.
  3. No-progress stop    — the same action repeated 3× halts the run as
                           `stalled` instead of burning the whole budget.

Run it:  python examples/m1_runtime.py
"""

from __future__ import annotations

import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from loopkit import (
    AnyOf,
    CompactingContext,
    CostModel,
    EventBus,
    Governor,
    Kernel,
    MaxIterations,
    NoProgress,
    ToolRegistry,
)
from loopkit.adapters import MockAdapter, act, final
from loopkit.sinks import MemorySink


def _registry() -> ToolRegistry:
    registry = ToolRegistry(allow_writes=[])

    @registry.tool("echo", "Echo a value back", schema={"value": "str"})
    def echo(args: dict) -> str:
        return f"echo:{args.get('value', '')}"

    return registry


def demo_compaction() -> None:
    print("\n[1] CONTEXT COMPACTION ---------------------------------------")
    registry = _registry()
    # Ten tool calls then an answer — enough history to force compaction.
    script = [act("echo", {"value": f"step-{i}"}, thought=f"call {i}") for i in range(10)]
    script.append(final("done after ten steps."))

    memory = MemorySink()
    bus = EventBus(run_id="m1-compaction", sinks=[memory])
    kernel = Kernel(
        adapter=MockAdapter(script),
        registry=registry,
        stop_policy=AnyOf(MaxIterations(50)),
        bus=bus,
        context_strategy=CompactingContext(keep_last=4),
    )
    result = kernel.run("Do ten echo steps then answer.")

    starts = memory.of_type("iteration.start")
    last = starts[-1].data
    dropped_seen = max(s.data.get("context_dropped", 0) for s in starts)
    print(f"  strategy        : {last['context_strategy']}")
    print(f"  final window    : {last['context_messages']} msgs")
    print(f"  max dropped     : {dropped_seen} messages compacted away")
    print(f"  summarized      : {last['context_summarized']}")
    assert result.status == "success"
    assert dropped_seen > 0, "compaction should have dropped middle messages"
    assert any(s.data.get("context_summarized") for s in starts), "expected a summary"
    print("  OK ✅  long history compacted, task still succeeded")


def demo_governor() -> None:
    print("\n[2] GOVERNOR TOKEN CAP ---------------------------------------")
    registry = _registry()
    # Each act = 48 tokens. Cap at 120 -> trips on the 3rd charge.
    script = [act("echo", {"value": f"v{i}"}, thought=f"call {i}") for i in range(20)]

    memory = MemorySink()
    bus = EventBus(run_id="m1-governor", sinks=[memory])
    governor = Governor(max_tokens=120, cost_model=CostModel(per_1k_in=1.0, per_1k_out=2.0))
    kernel = Kernel(
        adapter=MockAdapter(script),
        registry=registry,
        stop_policy=AnyOf(MaxIterations(50)),
        bus=bus,
        governor=governor,
    )
    result = kernel.run("Echo forever (until the governor stops you).")

    stop = memory.of_type("stop.check")[-1].data
    end = memory.of_type("run.end")[-1].data
    print(f"  stop policy     : {stop['policy']}")
    print(f"  reason          : {stop['reason']}")
    print(f"  status          : {result.status}")
    print(f"  usage           : {end['governor']}")
    assert result.status == "budget_exceeded", result.status
    assert stop["policy"] == "governor"
    assert end["governor"]["cost"] > 0
    print("  OK ✅  hard token rail engaged, run halted")


def demo_no_progress() -> None:
    print("\n[3] NO-PROGRESS DETECTION ------------------------------------")
    registry = _registry()
    # Same action, same args, three times -> stalled.
    script = [act("echo", {"value": "same"}, thought="try again") for _ in range(6)]

    memory = MemorySink()
    bus = EventBus(run_id="m1-noprogress", sinks=[memory])
    kernel = Kernel(
        adapter=MockAdapter(script),
        registry=registry,
        stop_policy=AnyOf(NoProgress(window=3), MaxIterations(50)),
        bus=bus,
    )
    result = kernel.run("Keep echoing the same thing.")

    stop = memory.of_type("stop.check")[-1].data
    print(f"  stop policy     : {stop['policy']}")
    print(f"  reason          : {stop['reason']}")
    print(f"  status          : {result.status}")
    print(f"  iterations      : {result.iterations}")
    assert result.status == "stalled", result.status
    assert result.iterations == 3, result.iterations
    print("  OK ✅  oscillation caught after 3 identical actions")


def main() -> None:
    print("=" * 62)
    print("LoopKit M1 — runtime rails (context, governor, no-progress)")
    print("=" * 62)
    demo_compaction()
    demo_governor()
    demo_no_progress()
    print("\n" + "=" * 62)
    print("ALL M1 CHECKS PASSED ✅")
    print("=" * 62)


if __name__ == "__main__":
    main()
