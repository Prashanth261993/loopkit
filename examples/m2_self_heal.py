"""m2_self_heal.py — the M2 self-heal features, proven with ZERO LLM.

M0 proved the loop runs; M1 made it *survivable*. M2 makes it *self-correcting*.
When a tool errors, a check fails, or a final answer is vetoed, a naive loop
either dies or blindly repeats. LoopKit instead routes the failure through a
small heal pipeline — critic -> Reflexion note -> bounded retry — and guards the
whole thing with an anti-thrash detector. Every demo below is deterministic and
CI-safe (MockAdapter, no network, no keys):

  1. Tool-error heal   — a flaky tool fails once, the critic files a TOOL_ERROR
                         critique, a reflexion note is injected, the retry works.
  2. Critic-reject     — a final answer that misses a requirement is vetoed; the
                         agent reflects and answers again, correctly.
  3. Anti-thrash       — an agent oscillating on the same action is stopped as
                         `thrashing` instead of burning the whole budget.

Run it:  python examples/m2_self_heal.py
"""

from __future__ import annotations

import sys

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
    ThrashDetector,
    ToolRegistry,
)
from loopkit.adapters import MockAdapter, act, final
from loopkit.sinks import MemorySink


def demo_tool_error_heal() -> None:
    print("\n[1] TOOL-ERROR HEAL ------------------------------------------")
    registry = ToolRegistry(allow_writes=[])
    calls = {"n": 0}

    @registry.tool("flaky", "Fails on first call, succeeds after", schema={})
    def flaky(args: dict) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient failure (attempt 1)")
        return "ok on retry"

    # First call fails -> heal -> the loop retries -> second call succeeds -> answer.
    script = [act("flaky", {}), act("flaky", {}), final("recovered and finished.")]

    memory = MemorySink()
    bus = EventBus(run_id="m2-tool-heal", sinks=[memory])
    kernel = Kernel(
        adapter=MockAdapter(script),
        registry=registry,
        stop_policy=AnyOf(MaxIterations(50)),
        bus=bus,
        critic=RuleBasedCritic(),
        heal_policy=HealPolicy(max_heals=3),
        reflexion=ReflexionMemory(),
    )
    result = kernel.run("Use the flaky tool, then answer.")

    trig = memory.of_type("heal.trigger")[-1].data
    end = memory.of_type("run.end")[-1].data
    print(f"  heal trigger    : {trig['trigger']}")
    print(f"  heal reason     : {trig['reason']}")
    print(f"  heals used      : {result.heals}")
    print(f"  reflexion log   : {end['heal']['reflexion']}")
    print(f"  status          : {result.status}")
    assert result.status == "success", result.status
    assert result.heals == 1, result.heals
    assert trig["trigger"] == "tool_error"
    assert memory.of_type("heal.retry"), "expected a heal.retry event"
    print("  OK ✅  transient failure healed, task still succeeded")


def demo_critic_reject() -> None:
    print("\n[2] CRITIC-REJECT HEAL ---------------------------------------")
    registry = ToolRegistry(allow_writes=[])

    def reject_final(answer: str) -> str | None:
        return None if "42" in answer else "answer must contain the number 42"

    # First answer misses the requirement -> vetoed -> reflect -> answer again.
    script = [final("the answer is unknown"), final("the answer is 42")]

    memory = MemorySink()
    bus = EventBus(run_id="m2-critic-reject", sinks=[memory])
    kernel = Kernel(
        adapter=MockAdapter(script),
        registry=registry,
        stop_policy=AnyOf(MaxIterations(50)),
        bus=bus,
        critic=RuleBasedCritic(reject_final=reject_final),
        heal_policy=HealPolicy(max_heals=3),
    )
    result = kernel.run("Answer the question (must cite 42).")

    trig = memory.of_type("heal.trigger")[-1].data
    print(f"  heal trigger    : {trig['trigger']}")
    print(f"  heal reason     : {trig['reason']}")
    print(f"  heals used      : {result.heals}")
    print(f"  final answer    : {result.result!r}")
    print(f"  status          : {result.status}")
    assert result.status == "success", result.status
    assert result.heals == 1, result.heals
    assert trig["trigger"] == "critic_reject"
    assert result.result == "the answer is 42"
    print("  OK ✅  bad final vetoed, corrected answer accepted")


def demo_anti_thrash() -> None:
    print("\n[3] ANTI-THRASH ----------------------------------------------")
    registry = ToolRegistry(allow_writes=[])

    @registry.tool("spin", "A harmless no-op the agent keeps repeating", schema={})
    def spin(args: dict) -> str:
        return "spun"

    # The tool never errors, so heal never fires — but the agent keeps making the
    # identical call. The thrash detector counts total repeats and pulls the plug.
    script = [act("spin", {"x": "same"}) for _ in range(5)]

    memory = MemorySink()
    bus = EventBus(run_id="m2-thrash", sinks=[memory])
    kernel = Kernel(
        adapter=MockAdapter(script),
        registry=registry,
        stop_policy=AnyOf(MaxIterations(50)),
        bus=bus,
        thrash_detector=ThrashDetector(threshold=3),
    )
    result = kernel.run("Keep calling spin forever.")

    thrash = memory.of_type("thrash.detected")[-1].data
    stop = memory.of_type("stop.check")[-1].data
    print(f"  signature       : {thrash['signature']}")
    print(f"  repeats         : {thrash['repeats']} (threshold {thrash['threshold']})")
    print(f"  stop policy     : {stop['policy']}")
    print(f"  status          : {result.status}")
    print(f"  iterations      : {result.iterations}")
    assert result.status == "thrashing", result.status
    assert thrash["repeats"] >= 3
    print("  OK ✅  oscillation caught, run halted before wasting the budget")


def main() -> None:
    print("=" * 62)
    print("LoopKit M2 — SELF-HEAL, proven with a scripted (zero-LLM) model")
    print("=" * 62)
    demo_tool_error_heal()
    demo_critic_reject()
    demo_anti_thrash()
    print("\nAll M2 self-heal demos passed. The loop corrects itself. ✅\n")


if __name__ == "__main__":
    main()
