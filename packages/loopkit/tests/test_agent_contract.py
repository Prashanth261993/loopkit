"""M4.5 — the Agent Contract + onboarding template.

These tests pin the promise the getting-started flow makes to a newcomer:
importing the copy-me template gives you an ``Agent`` whose two faces both work
end to end — ``demo`` heals to a correct answer, and ``grade`` shows the naive
arm failing where self-heal succeeds. If the front door breaks, CI says so.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# The onboarding template lives in examples/, which is not an installed package;
# put it on the path the same way a reader running `python examples/...` would.
_EXAMPLES = Path(__file__).resolve().parents[3] / "examples"
if str(_EXAMPLES) not in sys.path:
    sys.path.insert(0, str(_EXAMPLES))


@pytest.fixture(scope="module")
def template():
    import your_first_agent as t  # noqa: PLC0415  (path set up above)

    return t


def test_agent_value_shape(template):
    from loopkit.agent import Agent

    agent = template.first_agent
    assert isinstance(agent, Agent)
    assert agent.name and agent.description and agent.goal
    assert callable(agent.make_kernel) and callable(agent.eval_tasks)


def test_demo_heals_to_success(template):
    from loopkit.agent import demo

    result, memory = demo(template.first_agent)
    # RUN face: the demo must reach a correct, critic-approved final answer,
    # and it must have actually exercised the heal path (that's the point).
    assert result.status == "success"
    assert "42" in (result.result or "")
    assert len(memory.events) > 0


def test_grade_discriminates_naive_vs_heal(template):
    from loopkit.agent import grade

    report = grade(template.first_agent)
    # GRADE face: same task, two arms. Naive ships the first (wrong) answer;
    # self-heal's critic vetoes it and the agent self-corrects to 100%.
    assert report.summaries["self-heal"].success_rate == 1.0
    assert report.summaries["naive"].success_rate < 1.0
