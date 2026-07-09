"""m0_zero_llm.py — prove the loop runs end-to-end with ZERO LLM.

This is LoopKit's M0 proof criterion. Using the MockAdapter we script a small
ReAct run and watch the kernel emit a complete, valid event stream:

    run.start -> (iteration.start -> model.* -> tool.*)xN -> stop.check -> run.end

The scripted agent:
  1. reverses a string via a safe tool
  2. tries to write a file via a DESTRUCTIVE tool -> dry-run (not on allow-list)
  3. gives its final answer

Run it:  python examples/m0_zero_llm.py
"""

from __future__ import annotations

import sys

# Windows consoles default to cp1252; force UTF-8 so status glyphs render.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pathlib import Path

from loopkit import EventBus, Kernel, ToolRegistry
from loopkit.adapters import MockAdapter, act, final
from loopkit.policies import AnyOf, MaxIterations, TokenBudget
from loopkit.sinks import JsonlSink, MemorySink, read_jsonl
from loopkit.tools import Tool

ARTIFACT = Path(__file__).resolve().parents[1] / "artifacts" / "m0_zero_llm.jsonl"


def build_registry() -> ToolRegistry:
    # No allow-list -> the destructive tool below stays in dry-run mode.
    registry = ToolRegistry(allow_writes=[])

    @registry.tool("reverse", "Reverse a string", schema={"text": "str"})
    def reverse(args: dict) -> str:
        return args["text"][::-1]

    def write_file(args: dict) -> str:  # would touch disk — gated by safety
        Path(args["path"]).write_text(args["content"], encoding="utf-8")
        return f"wrote {args['path']}"

    registry.register(
        Tool(
            name="write_file",
            description="Write content to a file (destructive)",
            handler=write_file,
            destructive=True,
            schema={"path": "str", "content": "str"},
        )
    )
    return registry


def main() -> None:
    registry = build_registry()

    script = [
        act("reverse", {"text": "loopkit"}, thought="I'll reverse the string first."),
        act(
            "write_file",
            {"path": "out.txt", "content": "tikpool"},
            thought="Now persist it (expect a dry-run — not allow-listed).",
        ),
        final(
            "Reversed 'loopkit' -> 'tikpool'. The write was a safe dry-run.",
            thought="Done; report the result and the safety outcome.",
        ),
    ]
    adapter = MockAdapter(script)

    stop = AnyOf(MaxIterations(10), TokenBudget(10_000))

    memory = MemorySink()
    with JsonlSink(ARTIFACT) as jsonl:
        bus = EventBus(run_id="m0-demo", sinks=[jsonl, memory])
        kernel = Kernel(
            adapter=adapter,
            registry=registry,
            stop_policy=stop,
            bus=bus,
            system_prompt="You are a careful agent. Think, act, then answer.",
        )
        result = kernel.run("Reverse the string 'loopkit' and save it to out.txt.")

    print("=" * 60)
    print(f"status      : {result.status}")
    print(f"iterations  : {result.iterations}")
    print(f"tokens      : in={result.tokens_in} out={result.tokens_out}")
    print(f"result      : {result.result}")
    print(f"events      : {len(memory.events)} -> {ARTIFACT}")
    print("=" * 60)

    # --- Self-verification: the event stream must be well-formed. ---
    types = [e.type.value for e in memory.events]
    assert types[0] == "run.start", "stream must open with run.start"
    assert types[-1] == "run.end", "stream must close with run.end"
    assert "tool.result" in types, "expected at least one tool result"
    assert result.status == "success", f"expected success, got {result.status}"

    # A destructive tool with no allow-list must have been dry-run, not executed.
    tool_results = memory.of_type("tool.result")
    write = next(e for e in tool_results if e.data["name"] == "write_file")
    assert write.data["dry_run"] is True, "destructive write should be dry-run"
    assert not Path("out.txt").exists(), "dry-run must not touch disk"

    # seq must be dense and ordered (replay/eval invariant).
    seqs = [e.seq for e in memory.events]
    assert seqs == list(range(len(seqs))), "seq must be contiguous and ordered"

    # Round-trip: what we recorded reloads into identical events (the seam holds).
    replayed = read_jsonl(ARTIFACT)
    assert len(replayed) == len(memory.events), "replay count mismatch"
    assert [e.type for e in replayed] == [e.type for e in memory.events]

    print("ALL CHECKS PASSED ✅  (zero-LLM loop, valid event stream, safety held)")


if __name__ == "__main__":
    main()
