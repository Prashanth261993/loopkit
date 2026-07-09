"""tools.py — the capability boundary, with safety built in.

Every side effect an agent can have passes through the :class:`ToolRegistry`.
That makes it the natural place to enforce LoopKit's locked safety decision:

  * destructive tools are **dry-run by default**
  * real writes require the caller to pass an explicit **allow-list**

The registry records that allow-list in ``run.start`` config, so any recorded
run is self-describing about what it was permitted to do.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Tool:
    name: str
    description: str
    handler: Callable[[dict[str, Any]], Any]
    destructive: bool = False
    schema: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    ok: bool
    output: Any = None
    error: str | None = None
    dry_run: bool = False


class ToolRegistry:
    def __init__(self, allow_writes: list[str] | None = None) -> None:
        self._tools: dict[str, Tool] = {}
        self.allow_writes: set[str] = set(allow_writes or [])

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def tool(
        self,
        name: str,
        description: str,
        *,
        destructive: bool = False,
        schema: dict[str, Any] | None = None,
    ) -> Callable[[Callable[[dict[str, Any]], Any]], Callable[[dict[str, Any]], Any]]:
        """Decorator form of :meth:`register`."""

        def wrap(fn: Callable[[dict[str, Any]], Any]) -> Callable[[dict[str, Any]], Any]:
            self.register(
                Tool(name=name, description=description, handler=fn,
                     destructive=destructive, schema=schema or {})
            )
            return fn

        return wrap

    def specs(self) -> list[dict[str, Any]]:
        """Tool descriptions handed to the model adapter."""
        return [
            {
                "name": t.name,
                "description": t.description,
                "destructive": t.destructive,
                "schema": t.schema,
            }
            for t in self._tools.values()
        ]

    def safety_config(self) -> dict[str, Any]:
        """Recorded into ``run.start`` so runs are self-describing."""
        return {
            "mode": "dry_run_by_default",
            "allow_writes": sorted(self.allow_writes),
            "destructive_tools": sorted(
                t.name for t in self._tools.values() if t.destructive
            ),
        }

    def execute(self, name: str, args: dict[str, Any]) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(ok=False, error=f"unknown tool: {name!r}")

        # Safety gate: destructive tools not on the allow-list never really run.
        if tool.destructive and tool.name not in self.allow_writes:
            return ToolResult(
                ok=True,
                dry_run=True,
                output=f"[dry-run] would execute {name}({args}) — not on allow-list",
            )

        try:
            return ToolResult(ok=True, output=tool.handler(args))
        except Exception as exc:  # surfaced to the heal branch from M2
            return ToolResult(ok=False, error=f"{type(exc).__name__}: {exc}")
