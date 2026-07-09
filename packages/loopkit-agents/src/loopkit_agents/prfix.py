"""prfix.py — the pr-fixer agent.

Same shape as its two siblings. The domain tool ``pr.tests`` is a deterministic
mini test-runner over a diff: a diff that still contains a planted defect
(``TODO`` / ``raise NotImplementedError``) "fails"; a clean diff "passes". The
agent must ship a diff whose tests pass *and* say so.

:func:`_tests_pass` is the one predicate used as both the critic veto and the
eval requirement.
"""

from __future__ import annotations

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
from loopkit.agent import Agent
from loopkit.evals.harness import Scenario, Task
from loopkit.sinks import MemorySink
from loopkit_tools import process

_DEFECTS = ("TODO", "raise NotImplementedError", "FIXME")

BROKEN_DIFF = "+def add(a, b):\n+    raise NotImplementedError  # TODO"
FIXED_DIFF = "+def add(a, b):\n+    return a + b"


def run_tests(diff: str) -> str:
    """Return 'tests: pass' iff the diff has no planted defect markers."""
    for marker in _DEFECTS:
        if marker in diff:
            return f"tests: fail ({marker} left in diff)"
    return "tests: pass"


def _tests_pass(answer: str) -> "str | None":
    """None to accept, or a reason to reject. Critic veto == eval requirement."""
    if "tests: pass" not in answer:
        return "final answer must report 'tests: pass'"
    if any(marker in answer for marker in _DEFECTS):
        return "final answer still contains an unresolved defect marker"
    return None


def _script() -> "list":
    return [
        act("pr.tests", {"diff": BROKEN_DIFF}),
        final("pushed a quick fix"),  # no 'tests: pass' -> vetoed
        act("pr.tests", {"diff": FIXED_DIFF}),
        final("implemented add(); tests: pass"),  # accepted
    ]


def _registry(allow: "list[str] | None") -> ToolRegistry:
    registry = ToolRegistry(allow_writes=allow or [])

    @registry.tool("pr.tests", "Run the test suite against a diff.", schema={})
    def pr_tests(args: dict) -> str:
        return run_tests(str(args.get("diff", "")))

    registry.register(process.run_command())  # destructive shared tool, gated by default
    return registry


def make_kernel(bus: EventBus, allow: "list[str] | None" = None) -> Kernel:
    return Kernel(
        adapter=MockAdapter(_script()),
        registry=_registry(allow),
        stop_policy=AnyOf(MaxIterations(20)),
        bus=bus,
        critic=RuleBasedCritic(reject_final=_tests_pass),
        heal_policy=HealPolicy(max_heals=3),
        reflexion=ReflexionMemory(),
    )


def eval_tasks() -> "list[Task]":
    def build() -> Scenario:
        return Scenario(
            registry=_registry(allow=[]),
            script=_script(),
            goal="Fix the PR so the tests pass, then report the passing status.",
        )

    def check(result: LoopResult, mem: MemorySink) -> "tuple[bool, str]":
        answer = result.result or ""
        ok = _tests_pass(answer) is None
        return ok, f"passing={ok!r} answer={answer!r}"

    return [
        Task(
            id="pr-green",
            build=build,
            check=check,
            requirement=_tests_pass,
            description="Final answer must report passing tests with no defect markers.",
        )
    ]


agent = Agent(
    name="pr-fixer",
    description="Fixes a failing PR; heals when it declares victory before the tests actually pass.",
    goal="Fix the PR so the tests pass, then report the passing status.",
    make_kernel=make_kernel,
    eval_tasks=eval_tasks,
)
