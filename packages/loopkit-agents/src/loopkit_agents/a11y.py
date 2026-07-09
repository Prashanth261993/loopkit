"""a11y.py — the a11y-auditor agent.

The most deterministic of the three M5 agents, so it goes first. Its domain
tool ``a11y.scan`` is a *real* (zero-dependency, stdlib-only) accessibility
linter: it finds concrete WCAG-adjacent defects in an HTML string. The agent's
job is to return HTML that scans clean.

The staff-level move — the same one the toy in ``examples/your_first_agent.py``
makes — is that **one function** (:func:`_scan_clean`) is used twice:

  * as the critic's ``reject_final`` (RUN face): a final answer that still
    contains violations is vetoed, forcing the loop to heal;
  * as the task's ``requirement`` (GRADE face): the eval measures success with
    the identical predicate.

"What we enforce" and "what we measure" are therefore the same code — they
cannot drift.
"""

from __future__ import annotations

import re

from loopkit import (
    AnyOf,
    EventBus,
    HealPolicy,
    Kernel,
    LoopResult,
    MaxIterations,
    ReflexionMemory,
    RuleBasedCritic,
    ToolRegistry,
)
from loopkit.adapters import MockAdapter, act, final
from loopkit.agent import Agent
from loopkit.evals.harness import Scenario, Task
from loopkit.sinks import MemorySink
from loopkit_tools import fs

# --- fixtures: a broken page and its accessible fix --------------------------
BROKEN_HTML = (
    "<html>\n"
    "  <body>\n"
    '    <img src="logo.png">\n'
    "    <button></button>\n"
    "  </body>\n"
    "</html>"
)

FIXED_HTML = (
    '<html lang="en">\n'
    "  <body>\n"
    '    <img src="logo.png" alt="Company logo">\n'
    "    <button>Menu</button>\n"
    "  </body>\n"
    "</html>"
)


# --- the real, deterministic scanner (also exposed as a tool) ----------------
def scan_html(html: str) -> "list[str]":
    """Return a list of accessibility violation codes found in ``html``.

    Intentionally small and stdlib-only, but genuinely checks the page:
      * ``html-lang``   — the root ``<html>`` element has no ``lang`` attribute
      * ``img-alt``     — an ``<img>`` is missing an ``alt`` attribute
      * ``empty-button``— a ``<button>`` has no text and no ``aria-label``
    """
    violations: list[str] = []

    root = re.search(r"<html\b[^>]*>", html, re.IGNORECASE)
    if root and "lang=" not in root.group(0).lower():
        violations.append("html-lang")

    for img in re.findall(r"<img\b[^>]*>", html, re.IGNORECASE):
        if "alt=" not in img.lower():
            violations.append("img-alt")

    for btn in re.findall(r"<button\b[^>]*>(.*?)</button>", html, re.IGNORECASE | re.DOTALL):
        if not btn.strip():
            violations.append("empty-button")

    return violations


def _scan_clean(answer: str) -> "str | None":
    """None to accept, or a reason string to reject.

    The single source of truth reused as both critic veto and eval requirement.
    """
    found = scan_html(answer)
    return None if not found else f"accessibility violations remain: {', '.join(sorted(set(found)))}"


def _script() -> "list":
    # 1. scan the page, 2. try to ship it unfixed (critic vetoes), 3. ship the fix.
    return [
        act("a11y.scan", {"html": BROKEN_HTML}),
        final(BROKEN_HTML),  # still broken -> vetoed, triggers a heal
        final(FIXED_HTML),  # clean -> accepted
    ]


def _registry(allow: "list[str] | None") -> ToolRegistry:
    registry = ToolRegistry(allow_writes=allow or [])

    @registry.tool("a11y.scan", "Scan an HTML string for accessibility violations.", schema={})
    def a11y_scan(args: dict) -> "list[str]":
        return scan_html(str(args.get("html", "")))

    # Register a shared write tool too, so the run's safety config visibly gates
    # a destructive capability even though the demo never needs a real write.
    registry.register(fs.write_file())
    return registry


# --- RUN face ----------------------------------------------------------------
def make_kernel(bus: EventBus, allow: "list[str] | None" = None) -> Kernel:
    return Kernel(
        adapter=MockAdapter(_script()),
        registry=_registry(allow),
        stop_policy=AnyOf(MaxIterations(20)),
        bus=bus,
        critic=RuleBasedCritic(reject_final=_scan_clean),
        heal_policy=HealPolicy(max_heals=3),
        reflexion=ReflexionMemory(),
    )


# --- GRADE face --------------------------------------------------------------
def eval_tasks() -> "list[Task]":
    def build() -> Scenario:
        return Scenario(
            registry=_registry(allow=[]),
            script=_script(),
            goal="Scan the page, then return HTML with no accessibility violations.",
        )

    def check(result: LoopResult, mem: MemorySink) -> "tuple[bool, str]":
        answer = result.result or ""
        found = scan_html(answer)
        return (not found), f"violations={sorted(set(found))!r}"

    return [
        Task(
            id="a11y-clean",
            build=build,
            check=check,
            requirement=_scan_clean,
            description="Final HTML must pass the a11y scan (0 violations).",
        )
    ]


agent = Agent(
    name="a11y-auditor",
    description="Fixes accessibility defects in HTML; heals when it ships a page that still fails the scan.",
    goal="Scan the page, then return HTML with no accessibility violations.",
    make_kernel=make_kernel,
    eval_tasks=eval_tasks,
)
