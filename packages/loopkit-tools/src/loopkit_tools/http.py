"""loopkit_tools/http.py — a read-only HTTP GET tool (stdlib urllib).

Non-destructive: a GET fetches, it does not mutate. Body is capped so a large
response can't flood the loop's context or event stream.
"""

from __future__ import annotations

import urllib.request
from typing import Any

from loopkit.tools import Tool

_MAX = 8000


def http_get() -> Tool:
    """``http.get`` — fetch a URL and return ``{status, body}`` (body truncated)."""

    def handler(args: dict[str, Any]) -> dict[str, Any]:
        url = args["url"]
        timeout = args.get("timeout", 15)
        req = urllib.request.Request(url, headers={"User-Agent": "loopkit-tools/0.1"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            raw = resp.read(_MAX + 1).decode("utf-8", errors="replace")
            status = resp.status
        body = raw if len(raw) <= _MAX else raw[:_MAX] + "\n...[truncated]"
        return {"status": status, "body": body}

    return Tool(
        name="http.get",
        description="HTTP GET a URL and return its status and (truncated) body.",
        handler=handler,
        schema={"url": "str", "timeout": "float?"},
    )


TOOLS = (http_get,)
