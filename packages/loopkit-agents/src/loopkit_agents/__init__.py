"""loopkit-agents — three thin, real agents built on the LoopKit kernel.

Each agent is the same shape (see :mod:`loopkit.agent`): tools + policies + a
goal, plus an eval suite that proves the loop helps. Import an agent and either
:func:`~loopkit.agent.demo` it (watch it heal) or :func:`~loopkit.agent.grade`
it (measure naive vs self-heal).

    from loopkit_agents import a11y_auditor
    from loopkit.agent import demo, grade

    result, memory = demo(a11y_auditor)   # RUN face
    report = grade(a11y_auditor)          # GRADE face
"""

from __future__ import annotations

from loopkit_agents import a11y, deps, prfix

a11y_auditor = a11y.agent
dep_updater = deps.agent
pr_fixer = prfix.agent

#: All shipped agents, in onboarding order (most deterministic first).
ALL_AGENTS = (a11y_auditor, dep_updater, pr_fixer)

__all__ = [
    "a11y",
    "deps",
    "prfix",
    "a11y_auditor",
    "dep_updater",
    "pr_fixer",
    "ALL_AGENTS",
]
