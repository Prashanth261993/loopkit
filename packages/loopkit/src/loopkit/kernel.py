"""kernel.py — the iteration engine.

This is the loop. It ties adapter + tools + stop policies together and narrates
everything through the event bus. In M0 it implements the core ReAct cycle:

    iteration.start -> model.request -> model.response
        -> (final?  goal reached, stop success)
        -> (tool?   tool.call -> tool.result, append observation)
    -> stop policy check -> repeat

Self-healing and anti-thrash (the heal.* / thrash.* events) land in M2; their
event types already exist in the schema so the seam doesn't move.
"""

from __future__ import annotations

from dataclasses import dataclass

from loopkit.adapters.base import ModelAdapter
from loopkit.events import EventBus, EventType, RunStatus
from loopkit.policies.stop import StopPolicy
from loopkit.state import KernelState
from loopkit.tools import ToolRegistry


@dataclass
class LoopResult:
    status: str
    result: str | None
    iterations: int
    tokens_in: int
    tokens_out: int


class Kernel:
    def __init__(
        self,
        adapter: ModelAdapter,
        registry: ToolRegistry,
        stop_policy: StopPolicy,
        bus: EventBus,
        system_prompt: str = "",
    ) -> None:
        self.adapter = adapter
        self.registry = registry
        self.stop_policy = stop_policy
        self.bus = bus
        self.system_prompt = system_prompt

    def run(self, task: str) -> LoopResult:
        state = KernelState(run_id=self.bus.run_id, task=task)
        if self.system_prompt:
            state.history.append({"role": "system", "content": self.system_prompt})
        state.history.append({"role": "user", "content": task})

        self.bus.emit(
            EventType.RUN_START,
            task=task,
            adapter=self.adapter.name,
            stop_policy=getattr(self.stop_policy, "name", type(self.stop_policy).__name__),
            safety=self.registry.safety_config(),
            tools=[s["name"] for s in self.registry.specs()],
        )

        while True:
            state.iteration += 1
            self.bus.iteration = state.iteration
            self.bus.emit(
                EventType.ITERATION_START,
                context_messages=len(state.history),
            )

            self.bus.emit(
                EventType.MODEL_REQUEST,
                adapter=self.adapter.name,
                messages=len(state.history),
                tools=len(self.registry.specs()),
            )
            result = self.adapter.complete(state.history, self.registry.specs())
            state.tokens_in += result.tokens_in
            state.tokens_out += result.tokens_out
            self.bus.emit(
                EventType.MODEL_RESPONSE,
                thought=result.thought,
                tool_call=(
                    {"name": result.tool_call.name, "args": result.tool_call.args}
                    if result.tool_call
                    else None
                ),
                final=result.final,
                tokens_in=result.tokens_in,
                tokens_out=result.tokens_out,
            )

            # --- Branch 1: the agent answered. Goal reached, stop success. ---
            if result.final is not None:
                state.status = RunStatus.SUCCESS.value
                state.result = result.final
                self.bus.emit(
                    EventType.STOP_CHECK,
                    policy="final_answer",
                    decision="stop",
                    status=state.status,
                )
                break

            # --- Branch 2: the agent acted. Run the tool, record observation. ---
            if result.tool_call is not None:
                name = result.tool_call.name
                args = result.tool_call.args
                self.bus.emit(EventType.TOOL_CALL, name=name, args=args)
                tool_result = self.registry.execute(name, args)
                self.bus.emit(
                    EventType.TOOL_RESULT,
                    name=name,
                    ok=tool_result.ok,
                    dry_run=tool_result.dry_run,
                    output=_truncate(tool_result.output),
                    error=tool_result.error,
                )
                state.last_action = (name, args)
                if result.thought:
                    state.history.append({"role": "assistant", "content": result.thought})
                observation = tool_result.error or str(tool_result.output)
                state.history.append(
                    {"role": "tool", "name": name, "content": observation}
                )

            # --- Involuntary termination: budgets, caps, no-progress. ---
            decision = self.stop_policy.check(state)
            if decision is not None:
                state.status = decision.status.value
                self.bus.emit(
                    EventType.STOP_CHECK,
                    policy=decision.policy,
                    decision="stop",
                    reason=decision.reason,
                    status=state.status,
                )
                break

        self.bus.emit(
            EventType.RUN_END,
            status=state.status,
            iterations=state.iteration,
            tokens_in=state.tokens_in,
            tokens_out=state.tokens_out,
            result=state.result,
        )
        return LoopResult(
            status=state.status,
            result=state.result,
            iterations=state.iteration,
            tokens_in=state.tokens_in,
            tokens_out=state.tokens_out,
        )


def _truncate(value: object, limit: int = 500) -> object:
    text = value if isinstance(value, str) else repr(value)
    return text if len(text) <= limit else text[:limit] + "…"
