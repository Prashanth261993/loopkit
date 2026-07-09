"""agent.py — the Agent Contract.

The thesis of LoopKit is that *a real agent = tools + policies*. This file makes
that literal. Every LoopKit agent — the toy in ``examples/your_first_agent.py``
and the three real agents shipped in M5 — is the exact same shape, with two
faces:

  * **RUN it**   — ``make_kernel(bus, allow)`` returns a fully wired
                   :class:`~loopkit.Kernel` (its tools + its chosen policies),
                   and ``goal`` is the task you hand it. This is the face the
                   observe dashboard and any plain script use.
  * **GRADE it** — ``eval_tasks()`` returns the deterministic M4
                   :class:`~loopkit.evals.harness.Task` suite that *proves* the
                   agent works. This is the face the eval harness uses.

Because the contract is tiny and uniform, onboarding into any agent is the same
page every time: read its tools, read its policies, call :func:`demo` to watch
it run, call :func:`grade` to measure it. No agent gets to be a special
snowflake — and that uniformity is the whole point.

This module deliberately lives *outside* ``loopkit/__init__`` (it is imported as
``loopkit.agent``) to avoid an import cycle: the harness it depends on imports
from the ``loopkit`` top level, so pulling it into package init would be
circular.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from loopkit import EventBus, Kernel, LoopResult
from loopkit.evals.harness import EvalReport, Task, run_suite
from loopkit.sinks import MemorySink

# The wiring function: given the event bus for this run and an optional safety
# allow-list for destructive tools, return a fully assembled kernel. Keeping the
# bus as a parameter (rather than baking one in) is what lets the same agent be
# observed live, replayed to JSONL, or graded in-memory — the caller chooses the
# sink. ``allow=None`` means dry-run only (safe by default).
KernelFactory = Callable[[EventBus, "list[str] | None"], Kernel]


@dataclass
class Agent:
    """One agent, expressed as data. No base class to subclass, no lifecycle to
    learn — just four fields. Compose an :class:`Agent` from your tools and
    policies and you are done.

    Attributes:
        name: Stable identifier, used in run ids and reports.
        description: One line on what the agent does.
        goal: The default task string handed to :func:`demo`.
        make_kernel: Builds the agent's wired kernel (its tools + policies).
        eval_tasks: Returns the agent's deterministic grading suite.
    """

    name: str
    description: str
    goal: str
    make_kernel: KernelFactory
    eval_tasks: Callable[[], "list[Task]"]


def demo(agent: Agent, *, allow: "list[str] | None" = None) -> "tuple[LoopResult, MemorySink]":
    """Run ``agent`` once on its default goal.

    Returns the :class:`~loopkit.LoopResult` and the :class:`MemorySink` holding
    the full event stream — the *same* stream the dashboard renders, so what you
    measure here and what a human sees there can never diverge. No side effects
    unless you pass an explicit ``allow`` list.
    """
    memory = MemorySink()
    bus = EventBus(run_id=f"demo-{agent.name}", sinks=[memory])
    kernel = agent.make_kernel(bus, allow)
    result = kernel.run(agent.goal)
    return result, memory


def grade(agent: Agent) -> EvalReport:
    """Grade ``agent`` on its own suite through the naive-vs-self-heal harness.

    This is the honest scorecard: the harness judges *task success* with
    independent checkers, never the loop's self-reported status. If an agent's
    ``eval_tasks`` are well designed, ``grade`` quantifies exactly how much its
    policies buy over a naive baseline.
    """
    return run_suite(agent.eval_tasks())
