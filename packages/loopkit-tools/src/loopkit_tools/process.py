"""loopkit_tools/process.py — subprocess tool.

Running an arbitrary command is the most dangerous thing an agent can do, so
``proc.run`` is flagged destructive: it is a dry-run unless the caller allow-lists
it. When it does run, output is captured and truncated so a runaway command can't
flood the event stream.
"""

from __future__ import annotations

import subprocess
from typing import Any

from loopkit.tools import Tool

_MAX = 4000  # cap captured stdout/stderr so the event stream stays bounded


def _clip(s: str) -> str:
    return s if len(s) <= _MAX else s[:_MAX] + f"\n...[+{len(s) - _MAX} chars truncated]"


def run_command() -> Tool:
    """``proc.run`` — run a command. **Destructive** (dry-run by default).

    args: ``{cmd: list[str], cwd?: str, timeout?: float}``
    """

    def handler(args: dict[str, Any]) -> dict[str, Any]:
        cmd = args["cmd"]
        if not isinstance(cmd, list):
            raise ValueError("proc.run expects cmd to be a list[str], not a shell string")
        proc = subprocess.run(  # noqa: S603 - caller-gated by the allow-list
            cmd,
            cwd=args.get("cwd"),
            capture_output=True,
            text=True,
            timeout=args.get("timeout", 120),
        )
        return {
            "returncode": proc.returncode,
            "stdout": _clip(proc.stdout),
            "stderr": _clip(proc.stderr),
        }

    return Tool(
        name="proc.run",
        description="Run a command (argv list) and capture its output.",
        handler=handler,
        destructive=True,
        schema={"cmd": "list[str]", "cwd": "str?", "timeout": "float?"},
    )


TOOLS = (run_command,)
