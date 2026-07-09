"""m5_agents.py — the three thin agents, proven and recorded with ZERO LLM.

M5 is the payoff of every layer below it: a *real* agent in LoopKit is nothing
but ``tools + policies``. This script imports the three shipped agents from the
``loopkit-agents`` package and, for each, does the two things the Agent Contract
promises:

  * **RUN** — ``demo(agent)``: run it once with no allow-list (zero real side
    effects), and confirm the self-heal loop turns a rejected answer into a good
    one.
  * **GRADE** — ``grade(agent)``: measure naive-vs-self-heal on the exact same
    predicate the critic enforced at runtime.

It also records the a11y-auditor's self-healing run to a JSONL **showcase**
artifact and drops a copy at ``dashboard/public/a11y_showcase.jsonl`` so the
dashboard (and the M6 GitHub Pages site) can replay a real agent healing itself
— a *different* run from the M3 ``sample.jsonl`` release-readiness fixture.

Run it:
    python examples/m5_agents.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from loopkit import EventBus
from loopkit.agent import demo, grade
from loopkit.sinks import JsonlSink
from loopkit_agents import ALL_AGENTS, a11y_auditor

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = REPO_ROOT / "artifacts" / "m5_a11y_showcase.jsonl"
SHOWCASE = REPO_ROOT / "dashboard" / "public" / "a11y_showcase.jsonl"


def prove_all() -> None:
    """RUN + GRADE every agent; assert the loop measurably helps each one."""
    print("=" * 64)
    print("LoopKit M5 — three thin agents (tools + policies), zero-LLM")
    print("=" * 64)
    for agent in ALL_AGENTS:
        result, _memory = demo(agent)
        report = grade(agent)
        naive = report.summaries["naive"].success_rate
        healed = report.summaries["self-heal"].success_rate
        print(f"\n### {agent.name}")
        print(f"  {agent.description}")
        print(f"  demo : status={result.status} heals={result.heals}")
        print(f"  grade: naive {naive:.0%}  ->  self-heal {healed:.0%}")
        assert result.status == "success", (agent.name, result.status)
        assert result.heals >= 1, (agent.name, "no heal")
        assert healed > naive, (agent.name, naive, healed)
    print("\n  OK  every agent heals at runtime and out-scores naive when graded")


def record_showcase() -> None:
    """Record the a11y-auditor's self-heal run to a replayable JSONL artifact."""
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    SHOWCASE.parent.mkdir(parents=True, exist_ok=True)

    sink = JsonlSink(ARTIFACT)
    bus = EventBus(run_id="m5-a11y-auditor", sinks=[sink])
    kernel = a11y_auditor.make_kernel(bus, None)
    result = kernel.run(a11y_auditor.goal)
    sink.close()
    shutil.copyfile(ARTIFACT, SHOWCASE)

    print("\n" + "=" * 64)
    print("  a11y-auditor showcase run recorded")
    print(f"  status     : {result.status}")
    print(f"  heals      : {result.heals}")
    print(f"  artifact   : {ARTIFACT.relative_to(REPO_ROOT)}")
    print(f"  dashboard  : {SHOWCASE.relative_to(REPO_ROOT)}")
    assert result.status == "success", result.status
    assert result.heals >= 1, result.heals
    print("  OK  a NEW replay fixture (distinct from M3 sample.jsonl)")


def main() -> None:
    prove_all()
    record_showcase()


if __name__ == "__main__":
    main()
