"""test_m1_runtime.py — the M1 runtime rails.

Covers the pure, hermetic surface of M1:
  * ContextStrategy: passthrough / windowed / compacting + summary rollup
  * Governor: token / cost / iteration / wall caps + incremental charge
  * NoProgress stop policy: oscillation detection
  * ReAct parser: final / action / fenced-json / graceful fallback
  * OpenAI message parser: tool_call / plain / malformed args
  * Kernel integration: compaction path stays correct; governor trips the run

M0's own tests (test_m0_loop.py) guard backward compatibility; these add M1.
"""

from __future__ import annotations

from loopkit import (
    AnyOf,
    CompactingContext,
    CostModel,
    EventBus,
    Governor,
    Kernel,
    MaxIterations,
    NoProgress,
    PassthroughContext,
    ToolRegistry,
    WindowedContext,
)
from loopkit.adapters import MockAdapter, act, final, parse_openai_message, parse_react_response
from loopkit.adapters.react import react_preamble
from loopkit.policies.context import default_summarize, estimate_tokens
from loopkit.sinks import MemorySink
from loopkit.state import KernelState, action_signature


# --------------------------------------------------------------------------- #
# Context strategies
# --------------------------------------------------------------------------- #
def _state_with(history: list[dict]) -> KernelState:
    st = KernelState(run_id="t", task="task")
    st.history = history
    return st


def _history(n: int) -> list[dict]:
    h: list[dict] = [{"role": "system", "content": "sys"}, {"role": "user", "content": "task"}]
    for i in range(n):
        h.append({"role": "assistant", "content": f"thought {i}"})
        h.append({"role": "tool", "name": "echo", "content": f"obs {i}"})
    return h


def test_passthrough_is_identity():
    hist = _history(5)
    res = PassthroughContext().build(_state_with(hist))
    assert res.messages == hist
    assert res.dropped == 0
    assert res.summary is None
    assert res.strategy == "passthrough"


def test_windowed_keeps_system_task_and_recent():
    hist = _history(10)  # 2 + 20 = 22 messages; 21 non-system after head
    res = WindowedContext(keep_last=4).build(_state_with(hist))
    # system + head(task) + last 4
    assert res.messages[0]["role"] == "system"
    assert res.messages[1]["content"] == "task"
    assert len(res.messages) == 1 + 1 + 4
    assert res.dropped > 0
    assert res.summary is None


def test_compacting_inserts_summary_message():
    hist = _history(10)
    res = CompactingContext(keep_last=4).build(_state_with(hist))
    assert res.summary is not None
    assert res.dropped > 0
    # A single synthetic summary message carries the dropped middle.
    summaries = [m for m in res.messages if m.get("name") == "context_summary"]
    assert len(summaries) == 1
    assert "compacted" in summaries[0]["content"]


def test_compacting_no_drop_when_history_small():
    hist = _history(1)  # tiny; nothing to compact
    res = CompactingContext(keep_last=6).build(_state_with(hist))
    assert res.dropped == 0
    assert res.summary is None


def test_default_summarize_counts_tools():
    dropped = [
        {"role": "tool", "name": "echo", "content": "a"},
        {"role": "tool", "name": "echo", "content": "b"},
        {"role": "assistant", "content": "thinking"},
    ]
    summary = default_summarize(dropped)
    assert "echo×2" in summary
    assert "compacted 3" in summary


def test_estimate_tokens_scales_with_content():
    small = estimate_tokens([{"role": "user", "content": "x" * 4}])
    big = estimate_tokens([{"role": "user", "content": "x" * 400}])
    assert big > small


# --------------------------------------------------------------------------- #
# Governor
# --------------------------------------------------------------------------- #
def test_governor_token_cap_trips():
    g = Governor(max_tokens=100)
    g.charge(tokens_in=40, tokens_out=20, iteration=1)
    assert g.check() is None
    g.charge(tokens_in=40, tokens_out=20, iteration=2)  # total 120 >= 100
    d = g.check()
    assert d is not None
    assert d.status.value == "budget_exceeded"
    assert d.policy == "governor"


def test_governor_iteration_cap_uses_max_iters():
    g = Governor(max_iterations=2)
    g.charge(tokens_in=1, tokens_out=1, iteration=1)
    assert g.check() is None
    g.charge(tokens_in=1, tokens_out=1, iteration=2)
    d = g.check()
    assert d is not None
    assert d.status.value == "max_iters"


def test_governor_cost_cap_and_incremental_charge():
    g = Governor(max_cost=0.10, cost_model=CostModel(per_1k_in=1.0, per_1k_out=2.0))
    delta = g.charge(tokens_in=1000, tokens_out=1000, iteration=1)  # 1.0 + 2.0 = 3.0
    assert round(delta, 3) == 3.0
    d = g.check()
    assert d is not None
    assert d.status.value == "budget_exceeded"
    assert "cost cap" in d.reason


def test_governor_uncapped_never_trips():
    g = Governor()
    for i in range(1, 100):
        g.charge(tokens_in=1000, tokens_out=1000, iteration=i)
    assert g.check() is None
    assert g.usage()["tokens"] == 99 * 2000


# --------------------------------------------------------------------------- #
# NoProgress
# --------------------------------------------------------------------------- #
def test_no_progress_fires_on_repeat():
    st = KernelState(run_id="t", task="task")
    sig = action_signature("echo", {"value": "x"})
    st.action_signatures = [sig, sig, sig]
    d = NoProgress(window=3).check(st)
    assert d is not None
    assert d.status.value == "stalled"


def test_no_progress_ignores_varied_actions():
    st = KernelState(run_id="t", task="task")
    st.action_signatures = [
        action_signature("echo", {"value": "a"}),
        action_signature("echo", {"value": "b"}),
        action_signature("echo", {"value": "c"}),
    ]
    assert NoProgress(window=3).check(st) is None


def test_action_signature_is_order_insensitive():
    a = action_signature("t", {"x": 1, "y": 2})
    b = action_signature("t", {"y": 2, "x": 1})
    assert a == b


# --------------------------------------------------------------------------- #
# ReAct parser
# --------------------------------------------------------------------------- #
def test_react_parses_final_answer():
    r = parse_react_response("Thought: done\nFinal Answer: 42")
    assert r.final == "42"
    assert r.thought == "done"
    assert r.tool_call is None


def test_react_parses_action_with_json():
    text = 'Thought: use echo\nAction: echo\nAction Input: {"value": "hi"}'
    r = parse_react_response(text)
    assert r.tool_call is not None
    assert r.tool_call.name == "echo"
    assert r.tool_call.args == {"value": "hi"}
    assert r.final is None


def test_react_handles_fenced_json_args():
    text = 'Action: echo\nAction Input: ```json\n{"value": "x"}\n```'
    r = parse_react_response(text)
    assert r.tool_call is not None
    assert r.tool_call.args == {"value": "x"}


def test_react_strips_backticks_from_tool_name():
    text = 'Action: `echo`\nAction Input: {"value": "y"}'
    r = parse_react_response(text)
    assert r.tool_call is not None
    assert r.tool_call.name == "echo"


def test_react_graceful_fallback_to_final():
    r = parse_react_response("I think the answer is blue.")
    assert r.final == "I think the answer is blue."
    assert r.tool_call is None


def test_react_preamble_lists_tools():
    pre = react_preamble([{"name": "echo", "description": "echo it", "parameters": {}}])
    assert "echo" in pre
    assert "Final Answer" in pre


# --------------------------------------------------------------------------- #
# OpenAI-native parser
# --------------------------------------------------------------------------- #
def test_openai_parses_tool_call():
    msg = {
        "content": None,
        "tool_calls": [
            {"function": {"name": "echo", "arguments": '{"value": "hi"}'}}
        ],
    }
    r = parse_openai_message(msg, {"prompt_tokens": 10, "completion_tokens": 5})
    assert r.tool_call is not None
    assert r.tool_call.name == "echo"
    assert r.tool_call.args == {"value": "hi"}
    assert r.tokens_in == 10
    assert r.tokens_out == 5


def test_openai_parses_plain_answer():
    r = parse_openai_message({"content": "hello world"})
    assert r.final == "hello world"
    assert r.tool_call is None


def test_openai_malformed_args_degrade_to_empty():
    msg = {"tool_calls": [{"function": {"name": "echo", "arguments": "{not json"}}]}
    r = parse_openai_message(msg)
    assert r.tool_call is not None
    assert r.tool_call.args == {}


# --------------------------------------------------------------------------- #
# Kernel integration
# --------------------------------------------------------------------------- #
def _echo_registry() -> ToolRegistry:
    reg = ToolRegistry(allow_writes=[])

    @reg.tool("echo", "Echo", schema={"value": "str"})
    def echo(args: dict) -> str:
        return f"echo:{args.get('value', '')}"

    return reg


def test_kernel_compaction_succeeds_and_reports_drops():
    script = [act("echo", {"value": f"s{i}"}) for i in range(8)]
    script.append(final("done"))
    mem = MemorySink()
    bus = EventBus(run_id="k-compact", sinks=[mem])
    kernel = Kernel(
        adapter=MockAdapter(script),
        registry=_echo_registry(),
        stop_policy=AnyOf(MaxIterations(50)),
        bus=bus,
        context_strategy=CompactingContext(keep_last=3),
    )
    result = kernel.run("many steps")
    assert result.status == "success"
    starts = mem.of_type("iteration.start")
    assert max(s.data["context_dropped"] for s in starts) > 0
    assert any(s.data["context_summarized"] for s in starts)


def test_kernel_governor_trips_budget_exceeded():
    script = [act("echo", {"value": f"s{i}"}) for i in range(20)]
    mem = MemorySink()
    bus = EventBus(run_id="k-gov", sinks=[mem])
    kernel = Kernel(
        adapter=MockAdapter(script),
        registry=_echo_registry(),
        stop_policy=AnyOf(MaxIterations(50)),
        bus=bus,
        governor=Governor(max_tokens=120),
    )
    result = kernel.run("echo until capped")
    assert result.status == "budget_exceeded"
    last_stop = mem.of_type("stop.check")[-1]
    assert last_stop.data["policy"] == "governor"
    end = mem.of_type("run.end")[-1]
    assert end.data["governor"]["tokens"] >= 120


def test_kernel_no_progress_stalls():
    script = [act("echo", {"value": "same"}) for _ in range(6)]
    mem = MemorySink()
    bus = EventBus(run_id="k-stall", sinks=[mem])
    kernel = Kernel(
        adapter=MockAdapter(script),
        registry=_echo_registry(),
        stop_policy=AnyOf(NoProgress(window=3), MaxIterations(50)),
        bus=bus,
    )
    result = kernel.run("repeat")
    assert result.status == "stalled"
    assert result.iterations == 3
