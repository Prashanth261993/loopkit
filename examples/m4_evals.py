"""m4_evals.py — naive vs self-heal, MEASURED (zero LLM).

M2 proved the loop *can* self-correct on a couple of hand-picked demos. M4
answers the harder question a staff engineer actually gets asked: **is it worth
it?** Self-healing spends extra iterations and tokens — what does that buy?

This runs a 5-task deterministic suite under two policies and grades each run
with an INDEPENDENT checker (task success), not the loop's own ``status``. The
punchline you'll see below: the naive loop reports ``status=success`` on four
wrong answers — it "succeeds" at 20% real task success. The self-healing loop's
critic vetoes those, the agent retries, and it lands 100% — for the price of a
few extra iterations. That is the tradeoff, quantified.

The report is also written to ``dashboard/public/evals.json`` so the M6
showcase can render the naive-vs-heal chart from the same numbers.

Run it:  python examples/m4_evals.py
"""

from __future__ import annotations

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from loopkit.evals import demo_suite, run_suite

OUT = Path(__file__).resolve().parents[1] / "dashboard" / "public" / "evals.json"


def main() -> None:
    print("=" * 66)
    print("LoopKit M4 — EVALS: naive vs self-heal, graded on TASK success")
    print("=" * 66)

    report = run_suite(demo_suite())

    print("\n" + report.to_markdown())

    naive = report.summaries["naive"]
    heal = report.summaries["self-heal"]
    lift = heal.success_rate - naive.success_rate
    extra_iters = heal.mean_iters - naive.mean_iters

    print("The tradeoff, in one line:")
    print(
        f"  self-heal lifts task success by {lift:+.0%} "
        f"({naive.success_rate:.0%} -> {heal.success_rate:.0%}) "
        f"for {extra_iters:+.1f} mean iterations and {heal.total_heals} heals."
    )
    print(
        "  Note every naive case reported status=success — a loop's own verdict\n"
        "  is not task success. Only an independent checker measures that."
    )

    OUT.write_text(report.to_json(), encoding="utf-8")
    print(f"\n  wrote {OUT}")

    # The whole thesis as an assertion: healing must strictly beat naive on task
    # success, and must not regress the already-correct control.
    assert heal.success_rate > naive.success_rate, "heal should beat naive"
    assert heal.success_rate == 1.0, heal.success_rate
    already = [c for c in report.cases if c.task_id == "already-correct"]
    assert all(c.passed for c in already), "both arms must pass the control"
    assert all(c.heals == 0 for c in already), "control must cost zero heals"

    print("\nAll M4 eval assertions passed. The tradeoff is real and measured. ✅\n")


if __name__ == "__main__":
    main()
