"""Every shipped agent must earn its place twice: it must *heal* when run, and
the self-heal arm must *out-score* the naive arm when graded. These tests hold
all three agents to that bar — parametrized so a new agent added to
``ALL_AGENTS`` is graded automatically.
"""

from __future__ import annotations

import pytest

from loopkit.agent import demo, grade
from loopkit_agents import ALL_AGENTS, a11y_auditor, dep_updater, pr_fixer


@pytest.mark.parametrize("agent", ALL_AGENTS, ids=lambda a: a.name)
def test_demo_heals_and_succeeds(agent):
    """The RUN face: with no allow-list (zero real side effects) the agent
    should ship a BAD answer, get vetoed, and heal to a GOOD one."""
    result, memory = demo(agent)
    assert result.status == "success", f"{agent.name}: {result.status}"
    assert result.heals >= 1, f"{agent.name} never healed"
    # The event stream the dashboard renders is the same one we assert on.
    assert len(memory.events) > 0
    kinds = {e.type for e in memory.events}
    assert "heal.trigger" in kinds, f"{agent.name} emitted no heal.trigger"


@pytest.mark.parametrize("agent", ALL_AGENTS, ids=lambda a: a.name)
def test_grade_self_heal_beats_naive(agent):
    """The GRADE face: the *same* predicate that vetoed the final answer at
    runtime is the task requirement here, so the loop that heals must measure
    strictly better than the loop that doesn't."""
    report = grade(agent)
    naive = report.summaries["naive"]
    healed = report.summaries["self-heal"]
    assert healed.success_rate > naive.success_rate, (
        f"{agent.name}: self-heal {healed.success_rate} "
        f"not > naive {naive.success_rate}"
    )
    assert naive.success_rate == 0.0
    assert healed.success_rate == 1.0
    assert healed.total_heals >= 1


def test_all_agents_registered():
    """The package advertises exactly the three agents, in onboarding order."""
    assert ALL_AGENTS == (a11y_auditor, dep_updater, pr_fixer)
    names = [a.name for a in ALL_AGENTS]
    assert names == ["a11y-auditor", "dep-updater", "pr-fixer"]


@pytest.mark.parametrize("agent", ALL_AGENTS, ids=lambda a: a.name)
def test_writes_are_gated_by_default(agent):
    """Each agent registers a destructive shared tool; with no allow-list the
    kernel must record an empty allow-list and a non-empty destructive set in
    run.start config, proving real side effects are gated."""
    _result, memory = demo(agent)
    start = next(e for e in memory.events if e.type == "run.start")
    safety = start.data["safety"]
    assert safety["allow_writes"] == []
    assert safety["destructive_tools"], f"{agent.name} registered no gated tool"
