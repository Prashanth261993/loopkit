"""adapters/openai_compat.py — native function-calling backend.

The OpenAI ``/chat/completions`` shape is a de-facto standard: OpenAI itself,
plus vLLM, Groq, Together, OpenRouter, and LM Studio all speak it. Models here
support **native tool calling** — they return structured ``tool_calls`` JSON
rather than ReAct text — so this adapter normalizes *that* shape into the same
:class:`ModelResult` the ReAct path produces. One kernel, both protocols.

Design choices:
* stdlib :mod:`urllib` only — the core stays zero-dependency.
* The provider-shape → :class:`ModelResult` translation lives in the pure
  function :func:`parse_openai_message`, which is fully unit-tested without any
  network. The class is a thin HTTP wrapper around it.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from loopkit.adapters.base import ModelResult, ToolCall


class OpenAICompatError(RuntimeError):
    pass


def tool_specs(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert LoopKit's lightweight tool specs to OpenAI ``tools`` schema."""
    specs: list[dict[str, Any]] = []
    for t in tools:
        specs.append(
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get(
                        "parameters",
                        {"type": "object", "properties": {}},
                    ),
                },
            }
        )
    return specs


def parse_openai_message(
    message: dict[str, Any], usage: dict[str, Any] | None = None
) -> ModelResult:
    """Normalize one ``choices[0].message`` (+ ``usage``) into a ModelResult.

    Pure and network-free so it can be exhaustively unit-tested. Handles both
    the tool-call branch (``message.tool_calls``) and the plain-answer branch
    (``message.content``). Malformed tool-call argument JSON degrades to ``{}``
    rather than exploding the loop.
    """
    usage = usage or {}
    tokens_in = int(usage.get("prompt_tokens", 0) or 0)
    tokens_out = int(usage.get("completion_tokens", 0) or 0)

    content = message.get("content") or ""
    tool_calls = message.get("tool_calls") or []

    if tool_calls:
        call = tool_calls[0]
        fn = call.get("function", {})
        name = fn.get("name", "")
        raw_args = fn.get("arguments", "{}")
        try:
            args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
            if not isinstance(args, dict):
                args = {"value": args}
        except (json.JSONDecodeError, TypeError):
            args = {}
        return ModelResult(
            text=content,
            thought=content or None,
            tool_call=ToolCall(name=name, args=args),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )

    return ModelResult(
        text=content,
        thought=None,
        final=content.strip(),
        tokens_in=tokens_in,
        tokens_out=tokens_out,
    )


class OpenAICompatibleAdapter:
    """Call any OpenAI-compatible ``/chat/completions`` endpoint.

    ``base_url`` points at the provider (e.g. ``https://api.openai.com/v1`` or a
    local ``http://localhost:8000/v1``). When ``use_tools`` is true the registry's
    tools are sent as native function specs; set it false to force plain-text
    answers. Only the pure parser is unit-tested; live calls run in guarded
    examples.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        api_key: str | None = None,
        use_tools: bool = True,
        temperature: float = 0.1,
        timeout: float = 120.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.use_tools = use_tools
        self.temperature = temperature
        self.timeout = timeout
        self.name = f"openai_compat:{model}"

    def complete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> ModelResult:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {k: v for k, v in m.items() if k in ("role", "content", "name")}
                for m in messages
            ],
            "temperature": self.temperature,
        }
        if self.use_tools and tools:
            payload["tools"] = tool_specs(tools)

        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=data,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError) as exc:
            raise OpenAICompatError(f"request failed ({self.base_url}): {exc}") from exc

        choices = body.get("choices", [])
        if not choices:
            raise OpenAICompatError(f"no choices in response: {body}")
        return parse_openai_message(choices[0].get("message", {}), body.get("usage"))


__all__ = [
    "OpenAICompatibleAdapter",
    "OpenAICompatError",
    "parse_openai_message",
    "tool_specs",
]
