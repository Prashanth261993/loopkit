# loopkit

The agent-loop kernel at the core of [LoopKit](../../README.md).

Framework-agnostic. Zero LLM dependencies in the core. Everything the loop does
is emitted as a versioned event stream that powers replay, evals, and the
dashboard.

```python
from loopkit import Kernel, EventBus, ToolRegistry
from loopkit.adapters import MockAdapter, act, final
from loopkit.policies import AnyOf, MaxIterations
from loopkit.sinks import JsonlSink

registry = ToolRegistry(allow_writes=[])          # destructive tools dry-run by default
adapter = MockAdapter([act("reverse", {"text": "loopkit"}), final("tikpool")])
bus = EventBus("demo", sinks=[JsonlSink("run.jsonl")])
kernel = Kernel(adapter, registry, AnyOf(MaxIterations(10)), bus)
kernel.run("reverse 'loopkit'")
```

Install (editable, from repo root):

```bash
pip install -e packages/loopkit[dev]
```

See `examples/m0_zero_llm.py` for a complete zero-LLM run.
