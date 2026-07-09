"""test_m4_evals.py — the eval harness must itself be trustworthy.

These tests pin the two properties that make the M4 story honest:
  1. The naive loop reports ``status=success`` on wrong answers — so grading on
     ``status`` would lie; the checker must catch the failure.
  2. Self-heal strictly beats naive on TASK success without regressing the
     already-correct control (and costs zero heals there).
Plus report-shape and determinism guards.
"""

from __future__ import annotations

import json

from loopkit.evals import (
    NAIVE,
    SELF_HEAL,
    EvalReport,
    demo_suite,
    run_suite,
)


def test_report_shape() -> None:
    report = run_suite(demo_suite())
    assert isinstance(report, EvalReport)
    # 5 tasks x 2 arms.
    assert len(report.cases) == 10
    assert set(report.summaries) == {"naive", "self-heal"}
    for s in report.summaries.values():
        assert s.n == 5
        assert 0.0 <= s.success_rate <= 1.0


def test_self_heal_beats_naive_on_task_success() -> None:
    report = run_suite(demo_suite())
    naive = report.summaries["naive"]
    heal = report.summaries["self-heal"]
    assert heal.success_rate > naive.success_rate
    assert heal.success_rate == 1.0
    assert naive.success_rate == 0.2  # only the already-correct control passes


def test_naive_reports_success_status_on_wrong_answers() -> None:
    """The core staff-level point: loop status != task success. Every naive case
    that FAILS the checker still reports status=success."""
    report = run_suite(demo_suite())
    naive_failures = [
        c for c in report.cases if c.arm == "naive" and not c.passed
    ]
    assert naive_failures, "expected naive to fail some tasks"
    for c in naive_failures:
        assert c.status == "success", (c.task_id, c.status)


def test_self_heal_does_not_tax_correct_runs() -> None:
    report = run_suite(demo_suite())
    control = [c for c in report.cases if c.task_id == "already-correct"]
    assert len(control) == 2
    for c in control:
        assert c.passed
        assert c.heals == 0


def test_healing_spends_more_compute() -> None:
    """Self-heal buys success with extra iterations — the tradeoff must show."""
    report = run_suite(demo_suite())
    naive = report.summaries["naive"]
    heal = report.summaries["self-heal"]
    assert heal.mean_iters > naive.mean_iters
    assert heal.total_heals == 4  # 4 corrected tasks, 1 heal each


def test_deterministic() -> None:
    a = run_suite(demo_suite())
    b = run_suite(demo_suite())
    assert a.to_json() == b.to_json()


def test_json_roundtrips() -> None:
    report = run_suite(demo_suite())
    payload = json.loads(report.to_json())
    assert "cases" in payload and "summaries" in payload
    assert len(payload["cases"]) == 10


def test_markdown_renders() -> None:
    md = run_suite(demo_suite()).to_markdown()
    assert "Per-arm summary" in md
    assert "self-heal" in md and "naive" in md


def test_arms_are_the_only_difference() -> None:
    """Same suite, single-arm runs, must reproduce the multi-arm numbers —
    proving the arm (policy), not scenario nondeterminism, drives the result."""
    naive_only = run_suite(demo_suite(), arms=(NAIVE,))
    heal_only = run_suite(demo_suite(), arms=(SELF_HEAL,))
    assert naive_only.summaries["naive"].success_rate == 0.2
    assert heal_only.summaries["self-heal"].success_rate == 1.0
