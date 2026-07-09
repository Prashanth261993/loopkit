"""loopkit_tools/fs.py — filesystem tools.

Reads are always safe. ``fs.write`` is flagged destructive so LoopKit's registry
turns it into a dry-run unless the caller explicitly allow-lists it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from loopkit.tools import Tool


def read_file() -> Tool:
    """``fs.read`` — return a text file's contents (utf-8, replace errors)."""

    def handler(args: dict[str, Any]) -> str:
        path = Path(args["path"])
        return path.read_text(encoding="utf-8", errors="replace")

    return Tool(
        name="fs.read",
        description="Read a UTF-8 text file and return its contents.",
        handler=handler,
        schema={"path": "str"},
    )


def list_dir() -> Tool:
    """``fs.list`` — list entry names in a directory (sorted)."""

    def handler(args: dict[str, Any]) -> list[str]:
        path = Path(args.get("path", "."))
        return sorted(p.name for p in path.iterdir())

    return Tool(
        name="fs.list",
        description="List the entry names in a directory.",
        handler=handler,
        schema={"path": "str"},
    )


def write_file() -> Tool:
    """``fs.write`` — write text to a file. **Destructive** (dry-run by default)."""

    def handler(args: dict[str, Any]) -> str:
        path = Path(args["path"])
        content = args["content"]
        path.parent.mkdir(parents=True, exist_ok=True)
        n = path.write_text(content, encoding="utf-8")
        return f"wrote {n} chars to {path}"

    return Tool(
        name="fs.write",
        description="Write text to a file, creating parent dirs as needed.",
        handler=handler,
        destructive=True,
        schema={"path": "str", "content": "str"},
    )


TOOLS = (read_file, list_dir, write_file)
