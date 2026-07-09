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
from loopkit.policies.context import ContextStrategy, PassthroughContext
from loopkit.policies.governor import Governor
from loopkit.policies.stop import StopPolicy
from loopkit.state import KernelState, action_signature
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
        context_strategy: ContextStrategy | None = None,
        governor: Governor | None = None,
    ) -> None:
        self.adapter = adapter
        self.registry = registry
        self.stop_policy = stop_policy
        self.bus = bus
        self.system_prompt = system_prompt
        # Defaults are inert on purpose: PassthroughContext + no governor means
        # the M0 event stream is byte-for-byte identical. M1 features only turn
        # on when the caller opts in.
        self.context_strategy = context_strategy or PassthroughContext()
        self.governor = governor

    def run(self, task: str) -> LoopResult:
        state = KernelState(run_id=self.bus.run_id, task=task)
        if self.system_prompt:
            state.history.append({"role": "system", "content": self.system_prompt})
        state.history.append({"role": "user", "content": task})

        run_start_extra: dict[str, object] = {
            "context_strategy": self.context_strategy.name,
        }
        if self.governor is not None:
            run_start_extra["governor"] = self.governor.snapshot()

        self.bus.emit(
            EventType.RUN_START,
            task=task,
            adapter=self.adapter.name,
            stop_policy=getattr(self.stop_policy, "name", type(self.stop_policy).__name__),
            safety=self.registry.safety_config(),
            tools=[s["name"] for s in self.registry.specs()],
            **run_start_extra,
        )

        while True:
            state.iteration += 1
            self.bus.iteration = state.iteration

            # Context management: compaction / windowing happens here, before the
            # model ever sees the history. Passthrough is the identity function.
            ctx = self.context_strategy.build(state)
            self.bus.emit(
                EventType.ITERATION_START,
                **ctx.describe(),
            )

            self.bus.emit(
                EventType.MODEL_REQUEST,
                adapter=self.adapter.name,
                messages=len(ctx.messages),
                tools=len(self.registry.specs()),
            )
            result = self.adapter.complete(ctx.messages, self.registry.specs())
            state.tokens_in += result.tokens_in
            state.tokens_out += result.tokens_out

            charged_cost = None
            if self.governor is not None:
                charged_cost = self.governor.charge(
                    tokens_in=result.tokens_in,
                    tokens_out=result.tokens_out,
                    iteration=state.iteration,
                )

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
                cost=charged_cost,
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
                state.action_signatures.append(action_signature(name, args))
                if result.thought:
                    state.history.append({"role": "assistant", "content": result.thought})
                observation = tool_result.error or str(tool_result.output)
                state.history.append(
                    {"role": "tool", "name": name, "content": observation}
                )

            # --- Governor: the always-on resource rail (opt-in). ---
            if self.governor is not None:
                gov = self.governor.check()
                if gov is not None:
                    state.status = gov.status.value
                    self.bus.emit(
                        EventType.STOP_CHECK,
                        policy=gov.policy,
                        decision="stop",
                        reason=gov.reason,
                        status=state.status,
                    )
                    break

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

        run_end_extra: dict[str, object] = {}
        if self.governor is not None:
            run_end_extra["governor"] = self.governor.usage()

        self.bus.emit(
            EventType.RUN_END,
            status=state.status,
            iterations=state.iteration,
            tokens_in=state.tokens_in,
            tokens_out=state.tokens_out,
            result=state.result,
            **run_end_extra,
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
