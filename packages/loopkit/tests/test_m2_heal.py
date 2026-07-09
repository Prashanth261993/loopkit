"""test_m2_heal.py — the M2 self-heal machinery.

Two layers:
  * Pure unit tests on the heal primitives (heal.py): critic verdicts, the heal
    budget, Reflexion memory, backoff spacing, and the thrash detector.
  * Kernel integration: tool-error heal, budget exhaustion, critic-reject retry,
    and anti-thrash — all through the deterministic MockAdapter.

M0/M1 tests guard backward compatibility; these prove the loop self-corrects and
that every heal addition stays inert unless a critic + heal policy are wired in.
"""

from __future__ import annotations

from loopkit import (
    AnyOf,
    EventBus,
    ExponentialBackoff,
    HealPolicy,
    HealTrigger,
    Kernel,
    MaxIterations,
    NoBackoff,
    ReflexionMemory,
    RuleBasedCritic,
    ThrashDetector,
    ToolRegistry,
)
from loopkit.adapters import MockAdapter, act, final
from loopkit.policies.heal import Critique
from loopkit.sinks import MemorySink
from loopkit.state import KernelState, action_signature
from loopkit.tools import ToolResult


# --------------------------------------------------------------------------- #
# RuleBasedCritic
# --------------------------------------------------------------------------- #
def _state() -> KernelState:
    return KernelState(run_id="t", task="task")


def test_critic_tool_error_trips_on_not_ok() -> None:
    critic = RuleBasedCritic()
    critique = critic.inspect_tool(_state(), ToolResult(ok=False, error="boom"))
    assert critique is not None
    assert critique.trigger is HealTrigger.TOOL_ERROR
    assert critique.reason == "boom"


def test_critic_tool_ok_no_predicate_is_silent() -> None:
    critic = RuleBasedCritic()
    assert critic.inspect_tool(_state(), ToolResult(ok=True, output="fine")) is None


def test_critic_test_fail_predicate_on_ok_result() -> None:
    def test_failed(tr: ToolResult) -> str | None:
        return "3 tests failed" if "FAILED" in str(tr.output) else None

    critic = RuleBasedCritic(test_failed=test_failed)
    critique = critic.inspect_tool(_state(), ToolResult(ok=True, output="FAILED"))
    assert critique is not None
    assert critique.trigger is HealTrigger.TEST_FAIL
    assert critique.reason == "3 tests failed"
    # A clean run stays silent.
    assert critic.inspect_tool(_state(), ToolResult(ok=True, output="passed")) is None


def test_critic_final_reject_only_when_predicate_vetoes() -> None:
    critic = RuleBasedCritic(reject_final=lambda a: None if "42" in a else "need 42")
    assert critic.inspect_final(_state(), "the answer is 42") is None
    critique = critic.inspect_final(_state(), "no idea")
    assert critique is not None
    assert critique.trigger is HealTrigger.CRITIC_REJECT
    assert "need 42" in critique.reason


def test_critic_final_no_predicate_never_rejects() -> None:
    assert RuleBasedCritic().inspect_final(_state(), "anything") is None


# --------------------------------------------------------------------------- #
# Critique rendering
# --------------------------------------------------------------------------- #
def test_critique_as_note_is_a_reflexion_system_message() -> None:
    note = Critique(
        trigger=HealTrigger.TOOL_ERROR, reason="boom", suggestion="try again", iteration=2
    ).as_note()
    assert note["role"] == "system"
    assert note["name"] == "reflexion"
    assert "iteration 2 tool_error: boom. Next time: try again" in note["content"]


# --------------------------------------------------------------------------- #
# HealPolicy budget
# --------------------------------------------------------------------------- #
def test_heal_policy_budget_exhausts() -> None:
    policy = HealPolicy(max_heals=2)
    st = _state()
    assert policy.should_heal(st)
    policy.record()
    assert policy.should_heal(st)
    policy.record()
    assert not policy.should_heal(st)
    assert policy.snapshot() == {"max_heals": 2, "heals_used": 2}


# --------------------------------------------------------------------------- #
# ReflexionMemory
# --------------------------------------------------------------------------- #
def test_reflexion_memory_add_summary_and_latest() -> None:
    mem = ReflexionMemory()
    assert mem.latest_note() is None
    assert mem.summary() == {"count": 0, "triggers": []}
    mem.add(Critique(HealTrigger.TOOL_ERROR, "a", "x", 0))
    mem.add(Critique(HealTrigger.CRITIC_REJECT, "b", "y", 1))
    assert mem.summary() == {"count": 2, "triggers": ["tool_error", "critic_reject"]}
    latest = mem.latest_note()
    assert latest is not None and "critic_reject" in latest["content"]


def test_reflexion_notes_keep_last_window() -> None:
    mem = ReflexionMemory(keep_last=2)
    for i in range(4):
        mem.add(Critique(HealTrigger.TOOL_ERROR, f"r{i}", "x", i))
    notes = mem.notes()
    assert len(notes) == 2
    assert "r2" in notes[0]["content"] and "r3" in notes[1]["content"]


# --------------------------------------------------------------------------- #
# Backoff
# --------------------------------------------------------------------------- #
def test_no_backoff_is_zero() -> None:
    assert NoBackoff().delay(5) == 0.0


def test_exponential_backoff_grows_and_caps() -> None:
    bo = ExponentialBackoff(base=0.5, factor=2.0, cap=8.0)
    assert bo.delay(1) == 0.5
    assert bo.delay(2) == 1.0
    assert bo.delay(3) == 2.0
    assert bo.delay(99) == 8.0  # capped


# --------------------------------------------------------------------------- #
# ThrashDetector
# --------------------------------------------------------------------------- #
def _sig_state(*sigs: str) -> KernelState:
    st = _state()
    st.action_signatures = list(sigs)
    return st


def test_thrash_counts_total_not_consecutive() -> None:
    det = ThrashDetector(threshold=3)
    a = action_signature("open", {})
    b = action_signature("close", {})
    # Interleaved A B A B A — never 3 in a row, but 3 total A's.
    st = _sig_state(a, b, a, b, a)
    assert det.repeats_of_latest(st) == 3
    assert det.check(st)


def test_thrash_below_threshold_is_silent() -> None:
    det = ThrashDetector(threshold=3)
    a = action_signature("open", {})
    assert not det.check(_sig_state(a, a))
    assert det.repeats_of_latest(_state()) == 0


# --------------------------------------------------------------------------- #
# Kernel integration
# --------------------------------------------------------------------------- #
def _run(script, **kw):
    memory = MemorySink()
    bus = EventBus(run_id="m2-test", sinks=[memory])
    registry = kw.pop("registry", ToolRegistry(allow_writes=[]))
    kernel = Kernel(
        adapter=MockAdapter(script),
        registry=registry,
        stop_policy=AnyOf(MaxIterations(50)),
        bus=bus,
        **kw,
    )
    result = kernel.run("task")
    return result, memory


def _flaky_registry(fail_times: int) -> ToolRegistry:
    registry = ToolRegistry(allow_writes=[])
    calls = {"n": 0}

    @registry.tool("flaky", "fails N times then works", schema={})
    def flaky(args: dict) -> str:
        calls["n"] += 1
        if calls["n"] <= fail_times:
            raise RuntimeError(f"transient {calls['n']}")
        return "ok"

    return registry


def test_tool_error_heals_then_succeeds() -> None:
    result, memory = _run(
        [act("flaky", {}), act("flaky", {}), final("done")],
        registry=_flaky_registry(fail_times=1),
        critic=RuleBasedCritic(),
        heal_policy=HealPolicy(max_heals=3),
    )
    assert result.status == "success"
    assert result.heals == 1
    triggers = [e.data["trigger"] for e in memory.of_type("heal.trigger")]
    assert triggers == ["tool_error"]
    assert memory.of_type("heal.retry")


def test_heal_budget_caps_retries() -> None:
    # Tool fails twice; budget is 1 -> only one heal, second failure is not healed,
    # the model then answers and the run still ends success (heal budget bounds it).
    result, memory = _run(
        [act("flaky", {}), act("flaky", {}), final("gave up but answering")],
        registry=_flaky_registry(fail_times=2),
        critic=RuleBasedCritic(),
        heal_policy=HealPolicy(max_heals=1),
    )
    assert result.heals == 1
    assert len(memory.of_type("heal.trigger")) == 1
    assert result.status == "success"


def test_critic_reject_then_retry_succeeds() -> None:
    result, memory = _run(
        [final("nope"), final("the answer is 42")],
        critic=RuleBasedCritic(reject_final=lambda a: None if "42" in a else "need 42"),
        heal_policy=HealPolicy(max_heals=3),
    )
    assert result.status == "success"
    assert result.result == "the answer is 42"
    assert result.heals == 1
    assert memory.of_type("heal.trigger")[-1].data["trigger"] == "critic_reject"


def test_critic_reject_budget_exhausted_accepts_final() -> None:
    # Budget 1: first final vetoed + healed, second final still bad but budget is
    # spent, so it is accepted rather than looping forever.
    result, _ = _run(
        [final("bad1"), final("bad2")],
        critic=RuleBasedCritic(reject_final=lambda a: "always bad"),
        heal_policy=HealPolicy(max_heals=1),
    )
    assert result.status == "success"
    assert result.result == "bad2"
    assert result.heals == 1


def test_anti_thrash_halts_run() -> None:
    registry = ToolRegistry(allow_writes=[])

    @registry.tool("spin", "no-op", schema={})
    def spin(args: dict) -> str:
        return "spun"

    result, memory = _run(
        [act("spin", {"x": "same"}) for _ in range(5)],
        registry=registry,
        thrash_detector=ThrashDetector(threshold=3),
    )
    assert result.status == "thrashing"
    thrash = memory.of_type("thrash.detected")[-1].data
    assert thrash["repeats"] >= 3
    assert thrash["threshold"] == 3


def test_heal_disabled_by_default_stays_inert() -> None:
    # No critic/heal_policy -> a tool error is just an observation; no heal events.
    result, memory = _run(
        [act("flaky", {}), final("done despite the error")],
        registry=_flaky_registry(fail_times=1),
    )
    assert result.status == "success"
    assert result.heals == 0
    assert memory.of_type("heal.trigger") == []
