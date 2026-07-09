"""harness.py — measure the loop, don't trust it.

M3 let a human *watch* a run. M4 lets a machine *judge* one — at scale, and
crucially, it judges **task success**, not the loop's self-reported ``status``.

That distinction is the whole point. A naive loop stops at the FIRST ``final``
the model emits and reports ``status="success"`` — even when that answer is
wrong. The kernel has no way to know; it did its job. So an eval that trusts
``status`` would score a broken agent 100%. The eval instead runs an
*independent deterministic checker* over the run's result and event stream, and
scores the two policies — **naive** (accept first answer) vs **self-heal**
(critic vetoes bad answers, agent retries) — head to head.

Everything here is zero-LLM and deterministic: tasks script a wrong first
answer and a correct later one; the naive arm accepts the wrong one and fails
the checker, the healing arm's critic rejects it and the agent self-corrects.
The report then quantifies the tradeoff: how much extra compute self-healing
spends, and how much task success it buys.

The harness reads the SAME event stream the dashboard reads (via
:class:`MemorySink`), so what you measure and what you see can never diverge.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from statistics import mean
from typing import Callable

from loopkit import (
    AnyOf,
    EventBus,
    HealPolicy,
    Kernel,
    LoopResult,
    MaxIterations,
    ReflexionMemory,
    RuleBasedCritic,
    ThrashDetector,
    ToolRegistry,
)
from loopkit.adapters import MockAdapter
from loopkit.sinks import MemorySink

# A checker is an INDEPENDENT grader. It never looks at ``result.status`` to
# decide pass/fail — it inspects the actual answer and the event stream. Returns
# (passed, human-readable detail).
Checker = Callable[[LoopResult, MemorySink], "tuple[bool, str]"]


@dataclass
class Scenario:
    """One concrete, replayable run setup: a fresh tool registry, a scripted
    model turn-list, and the goal string. Built fresh per run because tools may
    carry state (counters, flakiness) that must reset between arms."""

    registry: ToolRegistry
    script: list
    goal: str


@dataclass
class Task:
    """A gradable unit of work, independent of the policy under test.

    ``build`` returns a fresh :class:`Scenario` on every call (never share
    stateful tools across runs). ``check`` is the deterministic grader.
    ``requirement`` is the rule the *healing* arm's critic enforces on a final
    answer (``None`` = accept, ``str`` = veto reason); the naive arm ignores it.
    Keeping ``check`` and ``requirement`` separate is deliberate: the grader is
    an outside observer, not the policy grading itself.
    """

    id: str
    build: Callable[[], Scenario]
    check: Checker
    requirement: Callable[[str], "str | None"] | None = None
    description: str = ""


@dataclass
class Arm:
    """A named loop policy. ``make_kernel`` wires a kernel for one run of one
    task. The two built-in arms below are the experiment: same script, same
    checker, different loop."""

    name: str
    make_kernel: Callable[[Task, Scenario, EventBus], Kernel]


def _naive_kernel(task: Task, scn: Scenario, bus: EventBus) -> Kernel:
    """The control: no critic, no heal. Accepts the first ``final`` verbatim."""
    return Kernel(
        adapter=MockAdapter(scn.script),
        registry=scn.registry,
        stop_policy=AnyOf(MaxIterations(50)),
        bus=bus,
    )


def _healing_kernel(task: Task, scn: Scenario, bus: EventBus) -> Kernel:
    """The treatment: a critic that enforces the task requirement can veto a
    bad final, routing the loop through reflect-and-retry instead of stopping."""
    critic = (
        RuleBasedCritic(reject_final=task.requirement)
        if task.requirement is not None
        else RuleBasedCritic()
    )
    return Kernel(
        adapter=MockAdapter(scn.script),
        registry=scn.registry,
        stop_policy=AnyOf(MaxIterations(50)),
        bus=bus,
        critic=critic,
        heal_policy=HealPolicy(max_heals=5),
        reflexion=ReflexionMemory(),
        thrash_detector=ThrashDetector(threshold=6),
    )


NAIVE = Arm("naive", _naive_kernel)
SELF_HEAL = Arm("self-heal", _healing_kernel)


@dataclass
class CaseResult:
    """The outcome of one (task, arm) run — the atom of the report."""

    task_id: str
    arm: str
    passed: bool
    status: str
    iterations: int
    tokens_in: int
    tokens_out: int
    heals: int
    detail: str

    @property
    def tokens(self) -> int:
        return self.tokens_in + self.tokens_out


@dataclass
class ArmSummary:
    """Aggregate metrics for one arm across the whole suite."""

    arm: str
    n: int
    passed: int
    success_rate: float
    mean_iters: float
    mean_tokens: float
    total_heals: int


@dataclass
class EvalReport:
    """The comparison. Holds every :class:`CaseResult` and derives one
    :class:`ArmSummary` per arm; renders to JSON (for the dashboard / M6) and
    Markdown (for humans and lessons)."""

    cases: list[CaseResult]
    summaries: dict[str, ArmSummary] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.summaries:
            self.summaries = self._summarize()

    def _summarize(self) -> dict[str, ArmSummary]:
        out: dict[str, ArmSummary] = {}
        arms: list[str] = []
        for c in self.cases:
            if c.arm not in arms:
                arms.append(c.arm)
        for arm in arms:
            rows = [c for c in self.cases if c.arm == arm]
            n = len(rows)
            passed = sum(1 for c in rows if c.passed)
            out[arm] = ArmSummary(
                arm=arm,
                n=n,
                passed=passed,
                success_rate=passed / n if n else 0.0,
                mean_iters=mean(c.iterations for c in rows) if rows else 0.0,
                mean_tokens=mean(c.tokens for c in rows) if rows else 0.0,
                total_heals=sum(c.heals for c in rows),
            )
        return out

    def to_json(self) -> str:
        return json.dumps(
            {
                "cases": [c.__dict__ for c in self.cases],
                "summaries": {a: s.__dict__ for a, s in self.summaries.items()},
            },
            indent=2,
        )

    def to_markdown(self) -> str:
        lines: list[str] = []
        lines.append("### Per-case results\n")
        lines.append("| task | arm | task success | loop status | iters | heals |")
        lines.append("|---|---|:---:|---|--:|--:|")
        for c in self.cases:
            mark = "PASS" if c.passed else "FAIL"
            lines.append(
                f"| {c.task_id} | {c.arm} | {mark} | {c.status} "
                f"| {c.iterations} | {c.heals} |"
            )
        lines.append("\n### Per-arm summary\n")
        lines.append("| arm | success rate | passed | mean iters | mean tokens | heals |")
        lines.append("|---|:---:|--:|--:|--:|--:|")
        for s in self.summaries.values():
            lines.append(
                f"| {s.arm} | {s.success_rate:.0%} | {s.passed}/{s.n} "
                f"| {s.mean_iters:.1f} | {s.mean_tokens:.0f} | {s.total_heals} |"
            )
        return "\n".join(lines) + "\n"


def run_suite(
    tasks: list[Task], arms: "tuple[Arm, ...]" = (NAIVE, SELF_HEAL)
) -> EvalReport:
    """Run every task under every arm and return the measured comparison. Each
    run gets a fresh scenario and its own :class:`MemorySink`, so runs are
    independent and the checker can inspect the full per-run event stream."""
    cases: list[CaseResult] = []
    for task in tasks:
        for arm in arms:
            scn = task.build()
            memory = MemorySink()
            bus = EventBus(run_id=f"eval-{task.id}-{arm.name}", sinks=[memory])
            kernel = arm.make_kernel(task, scn, bus)
            result = kernel.run(scn.goal)
            passed, detail = task.check(result, memory)
            cases.append(
                CaseResult(
                    task_id=task.id,
                    arm=arm.name,
                    passed=passed,
                    status=result.status,
                    iterations=result.iterations,
                    tokens_in=result.tokens_in,
                    tokens_out=result.tokens_out,
                    heals=result.heals,
                    detail=detail,
                )
            )
    return EvalReport(cases)
