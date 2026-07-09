"""adapters/react.py — prompt-based tool calling (the ReAct protocol).

Not every model speaks native function-calling JSON. The classic, universal
fallback is **ReAct** (Reason + Act): you *prompt* the model to emit a rigid
text shape —

    Thought: <reasoning>
    Action: <tool name>
    Action Input: <json args>

— or, when it's done:

    Thought: <reasoning>
    Final Answer: <answer>

LoopKit normalizes that text into the exact same :class:`ModelResult` a native
tool-calling adapter produces, so the kernel is blissfully unaware of which
protocol the underlying model used. This module is pure string-parsing with no
network — which is why the parser gets the heaviest unit-test coverage in M1.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from loopkit.adapters.base import ModelResult, ToolCall


@dataclass
class TextCompletion:
    """What a raw text backend returns: the text plus token counts.

    Real backends (Ollama, an OpenAI-compatible completion endpoint) produce
    this; :class:`ReActAdapter` turns it into a normalized :class:`ModelResult`.
    """

    text: str
    tokens_in: int = 0
    tokens_out: int = 0


def react_preamble(tools: list[dict[str, Any]]) -> str:
    """Build the system instructions that teach a model the ReAct shape.

    ``tools`` uses the same lightweight spec the registry exposes:
    ``{"name": ..., "description": ..., "parameters": {...}}``.
    """
    lines = [
        "You are a tool-using agent. Work in a strict loop.",
        "On each turn output EXACTLY one of these two shapes and nothing else.",
        "",
        "To use a tool:",
        "Thought: <your reasoning>",
        "Action: <one tool name from the list>",
        'Action Input: <a single-line JSON object of arguments>',
        "",
        "To finish:",
        "Thought: <your reasoning>",
        "Final Answer: <the answer for the user>",
        "",
        "Available tools:",
    ]
    for t in tools:
        desc = t.get("description", "")
        params = t.get("parameters", {})
        lines.append(f"- {t['name']}: {desc} params={json.dumps(params)}")
    if not tools:
        lines.append("- (none registered; you can only give a Final Answer)")
    return "\n".join(lines)


_ACTION_INPUT_RE = re.compile(r"Action\s*Input\s*:\s*(.*)", re.IGNORECASE | re.DOTALL)
_ACTION_RE = re.compile(r"Action\s*:\s*(.+)", re.IGNORECASE)
_THOUGHT_RE = re.compile(r"Thought\s*:\s*(.+)", re.IGNORECASE)
_FINAL_RE = re.compile(r"Final\s*Answer\s*:\s*(.*)", re.IGNORECASE | re.DOTALL)


def _extract_json(blob: str) -> dict[str, Any]:
    """Best-effort JSON extraction from a possibly-fenced, possibly-noisy blob."""
    blob = blob.strip()
    # Strip a leading ```json / ``` fence and its closing fence.
    if blob.startswith("```"):
        blob = re.sub(r"^```[a-zA-Z]*\n?", "", blob)
        blob = re.sub(r"\n?```$", "", blob).strip()
    # Stop at the first blank line / next section keyword if the model kept going.
    blob = re.split(r"\n\s*\n|\nThought:|\nAction:|\nFinal Answer:", blob)[0].strip()
    try:
        parsed = json.loads(blob)
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    except json.JSONDecodeError:
        # Fall back to the first {...} span we can find.
        m = re.search(r"\{.*\}", blob, re.DOTALL)
        if m:
            try:
                parsed = json.loads(m.group(0))
                return parsed if isinstance(parsed, dict) else {"value": parsed}
            except json.JSONDecodeError:
                pass
    return {}


def parse_react_response(text: str, tokens_in: int = 0, tokens_out: int = 0) -> ModelResult:
    """Parse a ReAct-formatted completion into a normalized :class:`ModelResult`.

    Robustness is the whole point: models drift from the format constantly. The
    rules, in order:

    * A ``Final Answer:`` present → it's a terminal answer (``final`` set).
    * Else an ``Action:`` present → a tool call (name + parsed JSON args).
    * Else → treat the entire text as an implicit final answer (graceful
      degradation beats crashing the loop).
    """
    thought_m = _THOUGHT_RE.search(text)
    thought = thought_m.group(1).strip() if thought_m else None

    final_m = _FINAL_RE.search(text)
    if final_m:
        answer = final_m.group(1).strip()
        return ModelResult(
            text=text,
            thought=thought,
            final=answer,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )

    action_m = _ACTION_RE.search(text)
    if action_m:
        name = action_m.group(1).strip().splitlines()[0].strip().strip("`").strip()
        input_m = _ACTION_INPUT_RE.search(text)
        args = _extract_json(input_m.group(1)) if input_m else {}
        return ModelResult(
            text=text,
            thought=thought,
            tool_call=ToolCall(name=name, args=args),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )

    # No recognizable structure — don't stall the loop, answer with what we got.
    return ModelResult(
        text=text,
        thought=thought,
        final=text.strip(),
        tokens_in=tokens_in,
        tokens_out=tokens_out,
    )


class ReActAdapter:
    """Wrap any text-in/text-out backend as a normalized :class:`ModelAdapter`.

    ``complete_text`` is the pluggable seam: give it a function that takes a
    prompt string and returns a :class:`TextCompletion`. Ollama and
    OpenAI-compatible *completion* endpoints both fit; so does a canned lambda in
    a unit test. The adapter renders messages + the ReAct preamble into a single
    prompt, calls the backend, and parses the reply.
    """

    def __init__(
        self,
        complete_text: Callable[[str], TextCompletion],
        name: str = "react",
    ) -> None:
        self._complete_text = complete_text
        self.name = name

    def render_prompt(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> str:
        parts = [react_preamble(tools), ""]
        for m in messages:
            role = m.get("role", "user")
            name = m.get("name")
            label = f"{role}/{name}" if name else role
            parts.append(f"[{label}] {m.get('content', '')}")
        parts.append("[assistant] ")
        return "\n".join(parts)

    def complete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> ModelResult:
        prompt = self.render_prompt(messages, tools)
        tc = self._complete_text(prompt)
        return parse_react_response(tc.text, tc.tokens_in, tc.tokens_out)


__all__ = [
    "TextCompletion",
    "ReActAdapter",
    "parse_react_response",
    "react_preamble",
]
