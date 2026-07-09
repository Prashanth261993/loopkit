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

import time
from collections.abc import Callable
from dataclasses import dataclass

from loopkit.adapters.base import ModelAdapter
from loopkit.events import EventBus, EventType, RunStatus
from loopkit.policies.context import ContextStrategy, PassthroughContext
from loopkit.policies.governor import Governor
from loopkit.policies.heal import (
    Backoff,
    Critic,
    Critique,
    HealPolicy,
    NoBackoff,
    ReflexionMemory,
    ThrashDetector,
)
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
    heals: int = 0


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
        critic: Critic | None = None,
        heal_policy: HealPolicy | None = None,
        reflexion: ReflexionMemory | None = None,
        thrash_detector: ThrashDetector | None = None,
        backoff: Backoff | None = None,
        sleep: Callable[[float], None] = time.sleep,
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
        # Self-heal (M2) is fully inert unless a critic AND a heal policy are
        # supplied, so M0/M1 runs emit no heal.*/thrash.* events.
        self.critic = critic
        self.heal_policy = heal_policy
        self.reflexion = reflexion or ReflexionMemory()
        self.thrash_detector = thrash_detector
        self.backoff = backoff or NoBackoff()
        self._sleep = sleep

    @property
    def _healing(self) -> bool:
        return self.critic is not None and self.heal_policy is not None

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
        if self._healing:
            run_start_extra["heal"] = {
                "critic": getattr(self.critic, "name", type(self.critic).__name__),
                "policy": self.heal_policy.name,
                "backoff": getattr(self.backoff, "name", type(self.backoff).__name__),
            }
        if self.thrash_detector is not None:
            run_start_extra["thrash"] = self.thrash_detector.name

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

            specs = self.registry.specs()
            self.bus.emit(
                EventType.MODEL_REQUEST,
                adapter=self.adapter.name,
                messages=len(ctx.messages),
                tools=len(specs),
                # Enriched so the dashboard can drill into *what* was sent, not
                # just how many. Content is truncated to keep the event small.
                message_previews=[_preview_message(m) for m in ctx.messages],
                tool_names=[s["name"] for s in specs],
            )
            result = self.adapter.complete(ctx.messages, specs)
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

            # --- Branch 1: the agent answered. Critic may still veto it. ---
            if result.final is not None:
                critique = None
                if self._healing and self.heal_policy.should_heal(state):
                    critique = self.critic.inspect_final(state, result.final)
                if critique is not None:
                    # Record what was proposed so the model sees its own rejected
                    # answer, then heal and loop instead of stopping success.
                    state.history.append(
                        {"role": "assistant", "content": result.final}
                    )
                    self._heal(state, critique)
                    continue
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

                # --- Anti-thrash (M2): oscillation guard on the signature stream.
                # Runs before heal so a loop that keeps healing the *same* failing
                # action is still stopped rather than retried forever.
                if self.thrash_detector is not None and self.thrash_detector.check(state):
                    sig = state.action_signatures[-1]
                    state.status = RunStatus.THRASHING.value
                    self.bus.emit(
                        EventType.THRASH_DETECTED,
                        signature=sig,
                        repeats=self.thrash_detector.repeats_of_latest(state),
                        threshold=self.thrash_detector.threshold,
                    )
                    self.bus.emit(
                        EventType.STOP_CHECK,
                        policy=self.thrash_detector.name,
                        decision="stop",
                        reason=f"action oscillating with no progress: {sig}",
                        status=state.status,
                    )
                    break

                # --- Self-heal (M2): route tool failures through critic + memory.
                if self._healing and self.heal_policy.should_heal(state):
                    critique = self.critic.inspect_tool(state, tool_result)
                    if critique is not None:
                        self._heal(state, critique)
                        continue

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
        if self._healing:
            run_end_extra["heal"] = {
                "heals": self.heal_policy.heals_used,
                "budget": self.heal_policy.max_heals,
                "reflexion": self.reflexion.summary(),
            }

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
            heals=self.heal_policy.heals_used if self._healing else 0,
        )

    def _heal(self, state: KernelState, critique: Critique) -> None:
        """Record a critique, inject a reflexion note, and back off before retry.

        Emits heal.trigger → heal.critique → heal.retry. The freshest reflexion
        note is appended to history so the next model turn sees the correction;
        the full log survives in ReflexionMemory for the run.end summary.
        """
        self.bus.emit(
            EventType.HEAL_TRIGGER,
            trigger=critique.trigger.value,
            reason=critique.reason,
            iteration=state.iteration,
        )
        self.bus.emit(
            EventType.HEAL_CRITIQUE,
            trigger=critique.trigger.value,
            suggestion=critique.suggestion,
        )
        self.reflexion.add(critique)
        state.history.append(critique.as_note())
        self.heal_policy.record()
        attempt = self.heal_policy.heals_used
        delay = self.backoff.delay(attempt)
        self.bus.emit(EventType.HEAL_RETRY, attempt=attempt, delay=delay)
        if delay > 0:
            self._sleep(delay)


def _truncate(value: object, limit: int = 500) -> object:
    text = value if isinstance(value, str) else repr(value)
    return text if len(text) <= limit else text[:limit] + "…"


def _preview_message(message: dict[str, object], limit: int = 120) -> dict[str, object]:
    """Compact, drill-down-friendly view of a context message.

    Keeps role + an optional tool ``name`` and a truncated content preview so
    the dashboard can show *what* the model saw without shipping full history.
    """
    content = str(message.get("content", ""))
    preview: dict[str, object] = {
        "role": message.get("role", "?"),
        "preview": content if len(content) <= limit else content[: limit - 1] + "…",
        "chars": len(content),
    }
    name = message.get("name")
    if name:
        preview["name"] = name
    return preview
