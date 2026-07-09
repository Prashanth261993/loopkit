"""suite.py — a deterministic, zero-LLM eval suite.

Five tasks, each built so the difference between the two arms is a *policy*
difference, never a scripting trick. Each task scripts the model to emit a
wrong/incomplete answer first and a correct one second (task 5 is correct on
the first try). The naive arm accepts whatever comes first; the healing arm's
critic enforces the task requirement and vetoes bad answers, so the agent
reflects and answers again.

Expected outcome (the headline of lesson 04):
  * naive     — passes only ``already-correct`` (1/5): it declares
                ``status=success`` on wrong answers everywhere else.
  * self-heal — passes all 5 (5/5), ties on ``already-correct`` with zero
                heals, so healing wins where it matters and costs nothing where
                the model was already right.

Shared by ``examples/m4_evals.py`` and ``tests/test_m4_evals.py`` so the demo
and the tests grade the identical suite.
"""

from __future__ import annotations

import json

from loopkit import LoopResult, ToolRegistry
from loopkit.adapters import act, final
from loopkit.evals.harness import Scenario, Task
from loopkit.sinks import MemorySink


def _cite_number() -> Task:
    """The final answer must cite the number 42."""

    def build() -> Scenario:
        return Scenario(
            registry=ToolRegistry(allow_writes=[]),
            script=[final("the answer is unknown"), final("the answer is 42")],
            goal="Answer the question — you must cite the number 42.",
        )

    def requirement(answer: str) -> "str | None":
        return None if "42" in answer else "answer must contain the number 42"

    def check(result: LoopResult, mem: MemorySink) -> "tuple[bool, str]":
        answer = result.result or ""
        ok = "42" in answer
        return ok, f"cited 42={ok!r} answer={answer!r}"

    return Task(
        id="cite-number",
        build=build,
        check=check,
        requirement=requirement,
        description="Final answer must contain '42'.",
    )


def _valid_json() -> Task:
    """The final answer must be a parseable JSON object."""

    def build() -> Scenario:
        return Scenario(
            registry=ToolRegistry(allow_writes=[]),
            script=[final("here you go: not json"), final('{"status": "ok"}')],
            goal="Reply with a JSON object describing the status.",
        )

    def _is_json_obj(answer: str) -> bool:
        try:
            return isinstance(json.loads(answer), dict)
        except (ValueError, TypeError):
            return False

    def requirement(answer: str) -> "str | None":
        return None if _is_json_obj(answer) else "answer must be a JSON object"

    def check(result: LoopResult, mem: MemorySink) -> "tuple[bool, str]":
        answer = result.result or ""
        ok = _is_json_obj(answer)
        return ok, f"valid_json={ok!r} answer={answer!r}"

    return Task(
        id="valid-json",
        build=build,
        check=check,
        requirement=requirement,
        description="Final answer must parse as a JSON object.",
    )


def _mention_keyword() -> Task:
    """The final answer must mention the required keyword."""

    def build() -> Scenario:
        return Scenario(
            registry=ToolRegistry(allow_writes=[]),
            script=[final("all done."), final("shipped it in loopkit.")],
            goal="Confirm where it shipped — mention 'loopkit'.",
        )

    def requirement(answer: str) -> "str | None":
        return None if "loopkit" in answer.lower() else "answer must mention 'loopkit'"

    def check(result: LoopResult, mem: MemorySink) -> "tuple[bool, str]":
        answer = result.result or ""
        ok = "loopkit" in answer.lower()
        return ok, f"mentions_keyword={ok!r} answer={answer!r}"

    return Task(
        id="mention-keyword",
        build=build,
        check=check,
        requirement=requirement,
        description="Final answer must mention 'loopkit'.",
    )


def _tool_then_answer() -> Task:
    """Must call the calculator tool AND cite its result in the answer.

    Both arms call the tool (turn 1 is an ``act``), so the discriminator is
    purely answer correctness: naive accepts the wrong sum, heal vetoes it.
    """

    def build() -> Scenario:
        registry = ToolRegistry(allow_writes=[])

        @registry.tool("add", "Add two integers a and b", schema={})
        def add(args: dict) -> str:
            return str(int(args["a"]) + int(args["b"]))

        return Scenario(
            registry=registry,
            script=[
                act("add", {"a": 3, "b": 4}),
                final("the sum is 12"),
                final("the sum is 7"),
            ],
            goal="Use the add tool on 3 and 4, then state the sum.",
        )

    def requirement(answer: str) -> "str | None":
        return None if "7" in answer else "answer must state the correct sum (7)"

    def check(result: LoopResult, mem: MemorySink) -> "tuple[bool, str]":
        answer = result.result or ""
        called = any(e.data.get("name") == "add" for e in mem.of_type("tool.result"))
        cited = "7" in answer
        ok = called and cited
        return ok, f"tool_called={called!r} cited_result={cited!r} answer={answer!r}"

    return Task(
        id="tool-then-answer",
        build=build,
        check=check,
        requirement=requirement,
        description="Must call add() and cite the correct sum (7).",
    )


def _already_correct() -> Task:
    """A control: the model is right on the first try. Both arms must pass, and
    the healing arm must spend zero heals — proving self-heal is not a tax on
    already-correct runs."""

    def build() -> Scenario:
        return Scenario(
            registry=ToolRegistry(allow_writes=[]),
            script=[final("the answer is 42")],
            goal="Answer the question — you must cite the number 42.",
        )

    def requirement(answer: str) -> "str | None":
        return None if "42" in answer else "answer must contain the number 42"

    def check(result: LoopResult, mem: MemorySink) -> "tuple[bool, str]":
        answer = result.result or ""
        ok = "42" in answer
        return ok, f"cited 42={ok!r} answer={answer!r}"

    return Task(
        id="already-correct",
        build=build,
        check=check,
        requirement=requirement,
        description="Model is correct first try; both arms should pass.",
    )


def demo_suite() -> list[Task]:
    """The full 5-task suite used by the example and the tests."""
    return [
        _cite_number(),
        _valid_json(),
        _mention_keyword(),
        _tool_then_answer(),
        _already_correct(),
    ]
