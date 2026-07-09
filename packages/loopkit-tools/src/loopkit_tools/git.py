"""loopkit_tools/git.py — git tools built on the git CLI.

Inspection (``git.status``, ``git.diff``) is safe. History-mutating tools
(``git.commit``, ``git.apply``) are flagged destructive and dry-run by default.
"""

from __future__ import annotations

import subprocess
from typing import Any

from loopkit.tools import Tool


def _git(cwd: str | None, *cliargs: str) -> str:
    proc = subprocess.run(  # noqa: S603
        ["git", *cliargs],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"git {cliargs[0]} failed")
    return proc.stdout


def git_status() -> Tool:
    """``git.status`` — porcelain status of the working tree."""

    def handler(args: dict[str, Any]) -> str:
        return _git(args.get("cwd"), "status", "--porcelain=v1", "--branch")

    return Tool(
        name="git.status",
        description="Show the working-tree status (porcelain).",
        handler=handler,
        schema={"cwd": "str?"},
    )


def git_diff() -> Tool:
    """``git.diff`` — unified diff of unstaged (or staged) changes."""

    def handler(args: dict[str, Any]) -> str:
        extra = ["--cached"] if args.get("staged") else []
        return _git(args.get("cwd"), "diff", *extra)

    return Tool(
        name="git.diff",
        description="Show a unified diff of working-tree (or staged) changes.",
        handler=handler,
        schema={"cwd": "str?", "staged": "bool?"},
    )


def git_commit() -> Tool:
    """``git.commit`` — commit staged changes. **Destructive** (dry-run by default)."""

    def handler(args: dict[str, Any]) -> str:
        return _git(args.get("cwd"), "commit", "-m", args["message"])

    return Tool(
        name="git.commit",
        description="Commit the staged changes with a message.",
        handler=handler,
        destructive=True,
        schema={"cwd": "str?", "message": "str"},
    )


def git_apply() -> Tool:
    """``git.apply`` — apply a patch. **Destructive** (dry-run by default)."""

    def handler(args: dict[str, Any]) -> str:
        proc = subprocess.run(  # noqa: S603
            ["git", "apply", "-"],
            cwd=args.get("cwd"),
            input=args["patch"],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or "git apply failed")
        return "patch applied"

    return Tool(
        name="git.apply",
        description="Apply a unified-diff patch to the working tree.",
        handler=handler,
        destructive=True,
        schema={"cwd": "str?", "patch": "str"},
    )


TOOLS = (git_status, git_diff, git_commit, git_apply)
