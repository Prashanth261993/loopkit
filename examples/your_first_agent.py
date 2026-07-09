"""your_first_agent.py — copy this file to build your own LoopKit agent.

A LoopKit agent is not a class hierarchy or a framework you learn. It is a
handful of tools, a few policies, and a goal — bundled into a plain
:class:`~loopkit.agent.Agent`. This file is the whole motion, end to end, with
zero LLM calls (a scripted ``MockAdapter`` stands in for the model), so it runs
anywhere in well under a second.

The toy agent below has one job: *answer citing the magic number*. That is
enough to show all three moving parts:

  1. a **tool** it can call,
  2. a **critic policy** that refuses a bad answer and makes the loop heal,
  3. an **eval** that proves, with numbers, that the policy actually helps.

Run it:

    python examples/your_first_agent.py

Then go build your own: change the tool, change the goal, change the check.
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
    LoopResult,
    MaxIterations,
    ReflexionMemory,
    RuleBasedCritic,
    ToolRegistry,
)
from loopkit.adapters import MockAdapter, act, final
from loopkit.agent import Agent, demo, grade
from loopkit.evals.harness import Scenario, Task
from loopkit.sinks import MemorySink

MAGIC = "42"


# --- the requirement: what a *good* answer looks like -----------------------
# One function, reused twice: the critic uses it to veto bad answers (RUN face),
# and the eval uses it to grade (GRADE face). Keeping them the same function is
# what stops "what we enforce" and "what we measure" from drifting apart.
def _must_cite_magic(answer: str) -> "str | None":
    """Return None to accept, or a reason string to reject."""
    return None if MAGIC in answer else f"answer must cite the magic number {MAGIC}"


# --- RUN face: the agent's tools + policies, wired into a Kernel -------------
def make_kernel(bus: EventBus, allow: "list[str] | None" = None) -> Kernel:
    registry = ToolRegistry(allow_writes=allow or [])

    @registry.tool("magic", "Return the magic number.", schema={})
    def magic(args: dict) -> str:
        return MAGIC

    # The model is scripted here so the demo is deterministic and LLM-free:
    #   1. call the `magic` tool,
    #   2. try to answer WITHOUT the number  -> the critic will veto this,
    #   3. answer again, correctly.
    adapter = MockAdapter(
        [
            act("magic", {}),
            final("the magic number is a secret"),  # vetoed -> triggers a heal
            final(f"the magic number is {MAGIC}"),  # accepted
        ]
    )

    return Kernel(
        adapter=adapter,
        registry=registry,
        stop_policy=AnyOf(MaxIterations(20)),
        bus=bus,
        # These two lines are the entire "self-healing" opt-in: a critic that
        # enforces the requirement, and a budget for how many times it may retry.
        critic=RuleBasedCritic(reject_final=_must_cite_magic),
        heal_policy=HealPolicy(max_heals=3),
        reflexion=ReflexionMemory(),
    )


# --- GRADE face: the deterministic suite that proves the agent works ---------
def eval_tasks() -> "list[Task]":
    def build() -> Scenario:
        # The eval builds its own scenario so the harness can swap policies
        # (naive vs self-heal) around the identical script and tools.
        registry = ToolRegistry(allow_writes=[])

        @registry.tool("magic", "Return the magic number.", schema={})
        def magic(args: dict) -> str:
            return MAGIC

        return Scenario(
            registry=registry,
            script=[
                act("magic", {}),
                final("the magic number is a secret"),
                final(f"the magic number is {MAGIC}"),
            ],
            goal="Call magic, then answer citing the number it returns.",
        )

    def check(result: LoopResult, mem: MemorySink) -> "tuple[bool, str]":
        answer = result.result or ""
        ok = MAGIC in answer
        return ok, f"cited {MAGIC}={ok!r} answer={answer!r}"

    return [
        Task(
            id="cite-magic",
            build=build,
            check=check,
            requirement=_must_cite_magic,
            description=f"Final answer must contain '{MAGIC}'.",
        )
    ]


# --- the agent: tools + policies + a goal, as data ---------------------------
first_agent = Agent(
    name="first-agent",
    description="Answers citing the magic number; heals when it forgets.",
    goal="Call magic, then answer citing the number it returns.",
    make_kernel=make_kernel,
    eval_tasks=eval_tasks,
)


def main() -> None:
    print("=== RUN: watch it heal ===")
    result, memory = demo(first_agent)
    print(f"status={result.status} answer={result.result!r} heals={result.heals}")
    print(f"events captured: {len(memory.events)} (this is what the dashboard renders)")

    print("\n=== GRADE: prove the policy helps ===")
    report = grade(first_agent)
    print(report.to_markdown())


if __name__ == "__main__":
    main()
