"""deps.py — the dep-updater agent.

Same shape as :mod:`loopkit_agents.a11y`. The domain tool ``deps.build`` is a
real, deterministic mini "build": it parses a requirements-style manifest and
fails if any dependency is left unpinned (``latest`` / ``*`` / a bare caret),
mirroring how a real update PR goes red when a floating version resolves to
something incompatible.

:func:`_build_green` is the single predicate used as *both* the critic veto and
the eval requirement.
"""

from __future__ import annotations

import re

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

_UNPINNED = re.compile(r"(==\s*)?(latest|\*)\s*$|[\^~]", re.IGNORECASE)

BROKEN_MANIFEST = "left-pad==latest\nrequests==2.31.0"
FIXED_MANIFEST = "left-pad==1.3.0\nrequests==2.31.0"


def build_manifest(manifest: str) -> str:
    """Return 'BUILD OK' iff every dependency line is exactly pinned."""
    for line in manifest.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if _UNPINNED.search(line) or "==" not in line:
            return f"BUILD FAILED: unpinned dependency: {line!r}"
    return "BUILD OK"


def _build_green(answer: str) -> "str | None":
    """None to accept, or a reason to reject. Reused as critic veto + eval requirement."""
    if "BUILD OK" not in answer:
        return "final answer must report a green build ('BUILD OK')"
    if _UNPINNED.search(answer):
        return "final answer still mentions an unpinned version (latest/*/^/~)"
    return None


def _script() -> "list":
    return [
        act("deps.build", {"manifest": BROKEN_MANIFEST}),
        final("bumped left-pad to latest"),  # unpinned + no BUILD OK -> vetoed
        act("deps.build", {"manifest": FIXED_MANIFEST}),
        final("pinned left-pad==1.3.0; BUILD OK"),  # green -> accepted
    ]


def _registry(allow: "list[str] | None") -> ToolRegistry:
    registry = ToolRegistry(allow_writes=allow or [])

    @registry.tool("deps.build", "Build a requirements manifest; fails on unpinned deps.", schema={})
    def deps_build(args: dict) -> str:
        return build_manifest(str(args.get("manifest", "")))

    registry.register(process.run_command())  # destructive shared tool, gated by default
    return registry


def make_kernel(bus: EventBus, allow: "list[str] | None" = None) -> Kernel:
    return Kernel(
        adapter=MockAdapter(_script()),
        registry=_registry(allow),
        stop_policy=AnyOf(MaxIterations(20)),
        bus=bus,
        critic=RuleBasedCritic(reject_final=_build_green),
        heal_policy=HealPolicy(max_heals=3),
        reflexion=ReflexionMemory(),
    )


def eval_tasks() -> "list[Task]":
    def build() -> Scenario:
        return Scenario(
            registry=_registry(allow=[]),
            script=_script(),
            goal="Update the dependency and report a green build with every version pinned.",
        )

    def check(result: LoopResult, mem: MemorySink) -> "tuple[bool, str]":
        answer = result.result or ""
        ok = _build_green(answer) is None
        return ok, f"green={ok!r} answer={answer!r}"

    return [
        Task(
            id="deps-green",
            build=build,
            check=check,
            requirement=_build_green,
            description="Final answer must report a pinned, green build.",
        )
    ]


agent = Agent(
    name="dep-updater",
    description="Updates dependencies and pins them; heals when a floating version leaves the build red.",
    goal="Update the dependency and report a green build with every version pinned.",
    make_kernel=make_kernel,
    eval_tasks=eval_tasks,
)
