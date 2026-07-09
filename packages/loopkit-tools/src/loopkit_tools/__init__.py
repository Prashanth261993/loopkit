"""loopkit-tools — shared, safety-aware tools for LoopKit agents.

The core ``loopkit`` package ships the *mechanism* (``ToolRegistry`` + the
dry-run/allow-list safety gate) but no concrete filesystem / process / git / http
handlers. This package provides those, each returned by a small factory so you can
register exactly what an agent needs::

    from loopkit import ToolRegistry
    from loopkit_tools import register_all, fs

    reg = ToolRegistry(allow_writes=["fs.write"])
    register_all(reg)                    # everything
    # or, selectively:
    reg.register(fs.read_file())

Destructive tools (``fs.write``, ``proc.run``, ``git.commit``, ``git.apply``) are
flagged ``destructive=True`` so they are dry-run unless allow-listed.
"""

from __future__ import annotations

from loopkit.tools import ToolRegistry

from loopkit_tools import fs, git, http, process

# The full catalogue: every factory across the four families.
ALL_FACTORIES = (*fs.TOOLS, *process.TOOLS, *git.TOOLS, *http.TOOLS)


def register_all(registry: ToolRegistry) -> ToolRegistry:
    """Register every tool in this package into ``registry`` and return it."""
    for factory in ALL_FACTORIES:
        registry.register(factory())
    return registry


__all__ = [
    "fs",
    "process",
    "git",
    "http",
    "ALL_FACTORIES",
    "register_all",
]
