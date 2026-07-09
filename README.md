<div align="center">

# 🔁 LoopKit

**A framework-agnostic agent-loop kernel — with observability, safety, and self-healing built in.**

*The model is a commodity. The loop around it is the engineering.*

</div>

---

LoopKit is a small Python kernel you wrap around **your own** LLM and tools. It
gives you the hard parts of an agent runtime — termination control, context
management, tool orchestration, self-healing, and a versioned event stream — so
that a real agent reduces to just **`tools + policies`**.

To prove the abstractions are real, LoopKit ships a family of thin, importable
agents built on the same kernel: a **PR Fixer**, a **Dependency Updater**, and
an **Accessibility Auditor**.

## Why this exists

Most "agent frameworks" bury the loop inside a monolith. LoopKit inverts that:
the loop is the product, and everything else — the model, the tools, the
stopping rules, the memory strategy — is a pluggable interface. The result is a
runtime you can **observe, test, and measure**.

## Architecture

```
Layer 4  dashboard/        React/TS — one consumer of the event stream, works for every agent
Layer 3  loopkit-agents/   pr-fixer · dep-updater · a11y-auditor  (importable, each w/ evals)
Layer 2  loopkit-tools/    shared tools: subprocess · fs · git · http
Layer 1  loopkit/          kernel · policies · events · evals · adapters   ← you are here (M0)
```

The **seam** between the Python kernel and the TypeScript dashboard is a single
versioned JSON event schema (`events.py`). The kernel emits events; a JSONL file
records them for replay/CI/evals, and a live sink streams them to the dashboard.
Both consumers read the *same* stream — so what you measure is exactly what you
see.

## Pluggable interfaces

| Interface | Purpose |
|---|---|
| `ModelAdapter` | bring your own LLM (OpenAI-compatible, Ollama, Anthropic, or a scripted mock) |
| `Tool` / `ToolRegistry` | user-registered capabilities, with a safety gate |
| `StopPolicy` (composable) | goal ∨ max-iters ∨ budget ∨ no-progress |
| `ContextStrategy` | compaction / summarization / Reflexion memory *(M1+)* |
| `HealPolicy` + `Critic` | swappable self-healing *(M2)* |
| `Sink` | JSONL, in-memory, live dashboard |

## Safety by default

Destructive tools (file writes, git, subprocess) are **dry-run by default**.
Real side effects require the caller to pass an explicit **allow-list**, enforced
at the `ToolRegistry` boundary and recorded in the run's `run.start` event — so
every recorded run is self-describing about what it was permitted to do.

## Quick start (zero LLM)

```bash
python -m venv .venv && .venv\Scripts\activate    # Windows
pip install -e packages/loopkit[dev]
python examples/m0_zero_llm.py
pytest
```

`examples/m0_zero_llm.py` runs the full loop with **no LLM and no network** using
the `MockAdapter`, then verifies the emitted event stream is well-formed and the
safety gate held.

## Status

Built inside-out, milestone by milestone:

- **M0 — Scaffold** ✅ kernel, event seam, mock adapter, JSONL sink, safety gate, zero-LLM loop
- **M1 — Runtime** ✅ composable stop policies, governor, context strategy, real adapters
- **M2 — Self-heal** ✅ actor–critic, retry/backoff, Reflexion memory, anti-thrash
- **M3 — Observe** ✅ SSE server + React dashboard (live + JSONL replay), drillable event rows
- **M4 — Evals** ✅ naive-vs-self-healing, graded on **task success** not loop status (+80pp, measured)
- **M5 — Agents ×3** · a11y-auditor → dep-updater → pr-fixer
- **M6 — Showcase** · static GitHub Pages replay dashboard

## License

MIT
