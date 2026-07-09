"""adapters/ollama.py — local, zero-key model backend.

Ollama is LoopKit's demo/CI default: it runs models like ``qwen2.5-coder`` on
your machine with no API key, so the whole showcase works offline and costs
nothing. It exposes a simple HTTP API; we hit ``/api/chat`` with the stdlib
:mod:`urllib` (no third-party HTTP dep — a hard requirement for the zero-deps
core) and drive it in **ReAct** mode, reusing :func:`parse_react_response`.

Network calls are never exercised in unit tests; examples guard on
reachability. What we *do* test is the pure ReAct parser this delegates to.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from loopkit.adapters.base import ModelResult
from loopkit.adapters.react import parse_react_response, react_preamble


class OllamaError(RuntimeError):
    pass


class OllamaAdapter:
    """Talk to a local Ollama server in ReAct mode.

    Parameters mirror the locked demo defaults: ``qwen2.5-coder`` on the standard
    local port. ``temperature`` defaults low for stable, parseable output.
    """

    def __init__(
        self,
        model: str = "qwen2.5-coder",
        host: str = "http://localhost:11434",
        *,
        temperature: float = 0.1,
        timeout: float = 120.0,
    ) -> None:
        self.model = model
        self.host = host.rstrip("/")
        self.temperature = temperature
        self.timeout = timeout
        self.name = f"ollama:{model}"

    def _build_messages(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> list[dict[str, str]]:
        """Prepend the ReAct system preamble to the conversation."""
        out: list[dict[str, str]] = [{"role": "system", "content": react_preamble(tools)}]
        for m in messages:
            role = m.get("role", "user")
            # Ollama only understands system/user/assistant/tool roles; map our
            # synthetic context-summary system messages straight through.
            content = m.get("content", "")
            if m.get("name"):
                content = f"({m['name']}) {content}"
            out.append({"role": role, "content": content})
        return out

    def complete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> ModelResult:
        payload = {
            "model": self.model,
            "messages": self._build_messages(messages, tools),
            "stream": False,
            "options": {"temperature": self.temperature},
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.host}/api/chat",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError) as exc:
            raise OllamaError(f"Ollama request failed ({self.host}): {exc}") from exc

        text = body.get("message", {}).get("content", "")
        tokens_in = int(body.get("prompt_eval_count", 0) or 0)
        tokens_out = int(body.get("eval_count", 0) or 0)
        return parse_react_response(text, tokens_in, tokens_out)


__all__ = ["OllamaAdapter", "OllamaError"]
