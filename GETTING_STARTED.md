# Getting Started with LoopKit

> **The thesis:** the model is a commodity; the *loop* around it is the
> engineering. A real agent is just **tools + policies**. LoopKit is the
> reusable loop — with observability, self-healing, and evals built in — so the
> only thing you write is your agent's tools and its policies.

This guide is a **ladder**. Each rung is one command, runs in under a second,
and needs **no API key** (every example is scripted with a `MockAdapter`, so you
learn the loop before you ever pay a token). Climb in order.

| Rung | You'll see | Command |
|---|---|---|
| **L0** | a full agent loop, start to finish | `python examples/m0_zero_llm.py` |
| **L1** | your own agent — 1 tool, 1 policy | `python examples/your_first_agent.py` |
| **L2** | self-healing, turned on with one flag | `python examples/m2_self_heal.py` |
| **L3** | the run, live, in a dashboard | `python examples/m3_observe.py` → open the console |
| **L4** | proof it works — naive vs healing, measured | `python examples/m4_evals.py` |
| **L5** | three real agents, same shape as yours | `python examples/m5_agents.py` |

---

## Install

```bash
git clone https://github.com/Prashanth261993/loopkit
cd loopkit
python -m venv .venv && . .venv/Scripts/activate     # Windows
# source .venv/bin/activate                          # macOS / Linux
pip install -e packages/loopkit
```

That's the whole runtime — **zero LLM dependencies**. LLM adapters are optional
extras (`pip install -e "packages/loopkit[openai]"`, `[anthropic]`, `[ollama]`)
you only need when you point an agent at a real model.

To run the three shipped agents (L5), also install the two agent-layer packages:

```bash
pip install -e packages/loopkit-tools -e packages/loopkit-agents
```

---

## L0 — See the loop

```bash
python examples/m0_zero_llm.py
```

An agent runs a task with no LLM at all: it thinks, calls a tool, gets a result,
decides it's done, and stops. Watch the event stream it prints — `run.start`,
`iteration.start`, `model.request/response`, `tool.call/result`, `stop.check`,
`run.end`. **Every** LoopKit run — yours, the demos, the M5 agents — emits this
same versioned stream. It is the one seam everything else reads from.

**Concept:** an agent loop is an OODA loop (observe → orient → decide → act) with
an explicit **stop policy**. The kernel owns the loop; you own the tools.

---

## L1 — Build your own agent

```bash
python examples/your_first_agent.py
```

Open [`examples/your_first_agent.py`](examples/your_first_agent.py) — it is
~40 lines and **it is the file you copy**. A LoopKit agent is a plain
`Agent(...)` value with four fields:

```python
from loopkit.agent import Agent, demo, grade

first_agent = Agent(
    name="first-agent",
    description="Answers citing the magic number; heals when it forgets.",
    goal="Call magic, then answer citing the number it returns.",
    make_kernel=make_kernel,   # RUN face:  your tools + your policies
    eval_tasks=eval_tasks,     # GRADE face: the suite that proves it works
)
```

Two faces, and that's the entire contract:

- **RUN it** — `make_kernel(bus, allow)` returns a wired `Kernel`. This is where
  you register tools (`@registry.tool(...)`) and choose policies (stop budget,
  critic, heal budget). `demo(agent)` runs it once and hands you the result plus
  the event stream.
- **GRADE it** — `eval_tasks()` returns a deterministic suite. `grade(agent)`
  scores it, naive-vs-self-heal, and never trusts the loop's own "success"
  claim.

Running it prints both faces: the demo heals once and answers correctly, then
the grade shows **naive 0% vs self-heal 100%** on the same task. That gap is the
rest of this guide.

**Now make it yours:** change the tool, change the `goal`, change the one-line
requirement. The loop, the healing, and the scoring come for free.

---

## L2 — Turn on self-healing

```bash
python examples/m2_self_heal.py
```

In L1 the agent healed because `make_kernel` wired two lines:

```python
critic=RuleBasedCritic(reject_final=_must_cite_magic),  # veto bad answers
heal_policy=HealPolicy(max_heals=3),                    # ...and allow N retries
```

That's the opt-in. A **critic** inspects a proposed final answer and either
accepts it or returns a reason to reject. On a reject the kernel emits
`heal.trigger` → `heal.critique`, writes a **Reflexion note** into context, and
lets the agent try again — bounded by the heal budget, guarded by a
`ThrashDetector` so it can't loop forever. Remove those two lines and the agent
is "naive": it ships the first thing the model says.

**Concept:** actor–critic. Generation is cheap and often wrong; a cheap,
deterministic critic that enforces the *requirement* is what turns a wrong-but-
confident answer into a correct one.

---

## L3 — Observe a run

```bash
python examples/m3_observe.py       # writes dashboard/public/sample.jsonl
cd dashboard && npm install && npm run dev
```

Open the console and hit **★ Play the sample run** — or upload any
`artifacts/*.jsonl` you've generated. You'll watch the timeline fill in, the
token/cost curve grow, tool calls resolve, and a **heal** land mid-run.

The dashboard is just *another reader of the same event stream* — no special
instrumentation. It works in three interchangeable modes:

- **JSONL replay** (zero backend — this is what GitHub Pages will host),
- **live SSE** (`python -m loopkit.observe ...` and tail `/events`),
- **file upload**.

**Concept:** if evals and humans read the *same* stream, what you measure and
what you see can never diverge.

---

## L4 — Grade it

```bash
python examples/m4_evals.py         # writes dashboard/public/evals.json
```

The eval harness runs each task twice — once **naive**, once **self-heal** —
and grades **task success** with an independent `Checker`, *never* the loop's
self-reported `status`. That distinction is the punchline:

> On the demo suite the naive arm reports `status=success` on **5/5** runs but
> is actually correct on only **1/5 (20%)**. Self-heal is correct on **5/5
> (100%)** — for +0.8 mean iterations and 4 heals — and ties the already-correct
> control at zero heals. Healing wins where it matters and costs nothing where
> the model was already right.

**Concept:** "the loop said success" is not "the task succeeded." An honest eval
judges the artifact, not the agent's opinion of itself.

---

## L5 — Read three real agents

```bash
pip install -e packages/loopkit-tools -e packages/loopkit-agents
python examples/m5_agents.py
```

Everything above was scaffolding for this moment: three *real* agents that are
nothing but `tools + policies`, built to the exact contract you learned in L1.

| Agent | Domain tool | Heals when… |
|---|---|---|
| **a11y-auditor** | scans HTML for accessibility defects | it ships a page that still fails the scan |
| **dep-updater** | builds a dependency manifest | a floating version leaves the build red |
| **pr-fixer** | runs the test suite | it declares victory before tests pass |

`m5_agents.py` runs `demo()` **and** `grade()` on each — every one heals once at
runtime and scores **naive 0% → self-heal 100%** when graded. The key discipline:
in each agent a *single* predicate function is passed to **both** the critic's
`reject_final` (the RUN face — what it enforces) and the eval task's
`requirement` (the GRADE face — what it's measured against). What you enforce is
literally what you measure; they cannot drift.

It also records the a11y-auditor's self-heal run to
`dashboard/public/a11y_showcase.jsonl` — drop it into the dashboard (L3) to watch
a real agent heal itself.

**Concept:** a good runtime makes agents *thin*. If adding a new agent means
writing a domain tool and one requirement predicate — not a new loop — the
abstraction is real.

---

## The mental model

```
your agent  =  tools  +  policies         (a plain Agent value)
                 │          │
       @registry.tool     stop / critic / heal / governor / context
                 │          │
                 ▼          ▼
            ┌─────────────────────┐
            │   LoopKit Kernel     │  ← owns the loop, emits ONE event stream
            └─────────┬───────────┘
                      │  events (versioned JSONL)
         ┌────────────┼────────────┐
         ▼            ▼             ▼
      evals       dashboard      your logs
   (grade it)   (observe it)   (whatever)
```

Onboarding into *your* agent and onboarding into any LoopKit agent is the same
page: read its tools, read its policies, `demo` it, `grade` it. Every agent in
M5 (a11y-auditor, dep-updater, pr-fixer) is built to this exact contract — which
means once you've read `your_first_agent.py`, you can read any of them.

## Next steps

- Copy `examples/your_first_agent.py`, swap in a real tool, and run `grade`.
- Point it at a real model: `pip install -e "packages/loopkit[ollama]"` and swap
  `MockAdapter` for `OllamaAdapter` (local, zero-key).
- Read the [README](README.md) for architecture and the layered ecosystem.
