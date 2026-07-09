# loopkit-agents

Three thin, real agents built on the [LoopKit](../loopkit) kernel. Each one is
the whole thesis in miniature: **a real agent = tools + policies**, plus an eval
that proves the loop actually helps.

Every agent has the identical shape (the [Agent Contract](../loopkit/src/loopkit/agent.py)):

| Face | Method | What it is |
|------|--------|------------|
| **RUN**   | `make_kernel(bus, allow)` | the agent's tools + its self-heal policies, wired into a `Kernel` |
| **GRADE** | `eval_tasks()`            | the deterministic naive-vs-self-heal suite that scores it |

And in every agent, **one function is both faces**: the critic's `reject_final`
(what we *enforce* at runtime) is literally the task's `requirement` (what we
*measure* in the eval). "What we enforce == what we measure", made physical.

## The agents

| Agent | Domain tool (real, offline) | Heals when… |
|-------|-----------------------------|-------------|
| `a11y-auditor` | `a11y.scan(html)` — finds `html-lang`, `img-alt`, `empty-button` defects | it ships HTML that still fails the scan |
| `dep-updater`  | `deps.build(manifest)` — fails on unpinned versions | it leaves a floating version and the build stays red |
| `pr-fixer`     | `pr.tests(diff)` — fails on planted defect markers | it declares victory before the tests pass |

Each also registers a shared **destructive** tool from
[`loopkit-tools`](../loopkit-tools) (`fs.write` / `proc.run`) so every run's
safety config visibly gates real side effects — writes are dry-run unless the
caller passes an explicit allow-list.

## Use it

```python
from loopkit_agents import a11y_auditor
from loopkit.agent import demo, grade

result, memory = demo(a11y_auditor)   # RUN: watch it heal (0 side effects)
print(result.status, result.heals)

report = grade(a11y_auditor)          # GRADE: naive vs self-heal, measured
print(report.to_markdown())
```

`memory.events` is the exact same event stream the observability dashboard
renders — so what you measure here and what a human watches there can never
diverge.
