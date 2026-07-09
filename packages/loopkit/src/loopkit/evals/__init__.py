"""evals — measure the loop, don't trust it.

M4's contribution: a deterministic, zero-LLM harness that scores **task
success** (via independent checkers) instead of the loop's self-reported
``status``, and reports a naive-vs-self-heal comparison.

    from loopkit.evals import run_suite, demo_suite

    report = run_suite(demo_suite())
    print(report.to_markdown())
"""

from loopkit.evals.harness import (
    NAIVE,
    SELF_HEAL,
    Arm,
    ArmSummary,
    CaseResult,
    Checker,
    EvalReport,
    Scenario,
    Task,
    run_suite,
)
from loopkit.evals.suite import demo_suite

__all__ = [
    "Arm",
    "ArmSummary",
    "CaseResult",
    "Checker",
    "EvalReport",
    "Scenario",
    "Task",
    "run_suite",
    "NAIVE",
    "SELF_HEAL",
    "demo_suite",
]
