import { ReplayEmbed } from "./ReplayEmbed";
import { EvalChart } from "./EvalChart";
import { Diagrams } from "./Diagrams";
import { Icon } from "./Icon";
import { Reveal, ScrollProgress } from "./motion";
import { LoopDraw } from "./LoopDraw";

const REPO = "https://github.com/Prashanth261993/loopkit";

// The observe console ships as index.html in dev + in the observe server bundle,
// but the Pages workflow promotes the showcase to the root index.html and moves
// the console to /console.html. Resolve the right href for whichever context
// this page is loaded in so the link never dead-ends.
const CONSOLE_HREF = import.meta.env.DEV ? "./index.html" : "./console.html";

// The "how thin is an agent?" snippet — the M4.5/M5 payoff in one screen. The
// same predicate is both the critic's reject_final (what the loop enforces at
// RUN time) and the eval task's requirement (what the harness measures at GRADE
// time). Enforce == measure, made physical.
const AGENT_SNIPPET = `def alt_text_present(answer: str) -> bool:
    """The ONE predicate. Used twice, never diverges."""
    return 'alt=' in answer and 'alt=""' not in answer

a11y_auditor = Agent(
    name="a11y-auditor",
    goal="emit an <img> with meaningful alt text",
    make_kernel=lambda adapter: build_kernel(
        adapter,
        tools=[write_html],
        # RUN face: critic vetoes any final answer that fails the predicate
        heal=RuleBasedCritic(reject_final=lambda a: not alt_text_present(a)),
        stop=GoalReached() | MaxIters(6),
    ),
    # GRADE face: the eval task scores the SAME predicate
    eval_tasks=[Task("alt-text", requirement=alt_text_present)],
)`;

const CONCEPTS = [
  {
    icon: Icon.stop,
    tag: "control",
    question: "When should it stop?",
    title: "Composable stop policies",
    sig: "GoalReached() | MaxIters(6) | Budget(...) | NoProgress()",
    body:
      "Termination is a first-class, testable object — not a buried while-condition. Policies OR together, so \"why did it stop?\" is always a named answer you can point to, never a mystery.",
  },
  {
    icon: Icon.heal,
    tag: "recovery",
    question: "What if the answer is wrong?",
    title: "Actor–critic self-healing",
    sig: "RuleBasedCritic(reject_final=...) -> Reflexion note",
    body:
      "A critic can veto a final answer or a failed tool call. Its verdict becomes a note injected back into context — counted against a heal budget separate from the governor — so the loop actually learns within a single run.",
  },
  {
    icon: Icon.thrash,
    tag: "safety",
    question: "What if it loops forever?",
    title: "Anti-thrash detection",
    sig: "hash(tool, normalize(args)) trips on oscillation",
    body:
      "A detector hashes each (tool, normalized args) and trips when the agent repeats itself in a different costume. Distinct from consecutive no-progress: this catches the loop going in circles overall.",
  },
  {
    icon: Icon.eye,
    tag: "observability",
    question: "How do you know what happened?",
    title: "One versioned event stream",
    sig: "emit(evt) -> JSONL file  +  live SSE  (drop-oldest)",
    body:
      "Every turn emits schema-versioned events, written once and fanned out drop-oldest to a JSONL file and a live SSE feed — so observability can never back-pressure the loop, and evals measure exactly what the dashboard showed.",
  },
];

export function Showcase() {
  return (
    <div className="showcase">
      <ScrollProgress />
      <TopBar />

      <header className="hero">
        <div className="hero-inner">
          <p className="eyebrow">
            <Icon.loop /> agent loop engineering
          </p>
          <h1>
            The model is a commodity.
            <br />
            <span className="grad">The loop around it is the engineering.</span>
          </h1>
          <p className="lede">
            <strong>LoopKit</strong> is a framework-agnostic agent-loop kernel in
            Python — composable stop policies, actor–critic self-healing,
            anti-thrash, and a versioned event stream that feeds both a live
            dashboard and a deterministic eval harness. Bring your own model;
            keep the engineering.
          </p>
          <div className="cta-row">
            <a className="btn primary" href={REPO} target="_blank" rel="noreferrer">
              <Icon.github /> View on GitHub
            </a>
            <a className="btn ghost" href={CONSOLE_HREF}>
              <Icon.eye /> Open the observe console
            </a>
          </div>
          <ul className="hero-stats">
            <li><b>4</b> layers, one seam</li>
            <li><b>91</b> tests, zero-LLM</li>
            <li><b>20% → 100%</b> naive vs self-heal</li>
          </ul>
        </div>
      </header>

      <main>
        <Section
          id="replay"
          eyebrow="watch it heal itself"
          title="A real run, replayed in your browser"
          note="Zero backend — a static JSONL file, paced by its own recorded timestamps, through the exact same reducer the live console uses."
        >
          <Reveal><ReplayEmbed /></Reveal>
          <p className="stage-caption">
            The a11y-auditor emits an <code>&lt;img&gt;</code> with no alt text,
            its critic vetoes the final answer, a Reflexion note is injected, and
            the retry passes — all visible on the timeline. Click any row to drill
            into the messages and tool calls behind it.
          </p>
        </Section>

        <Section
          id="concepts"
          eyebrow="the ideas"
          title="Four hard questions"
          note="Writing a loop is trivial. Running one well means answering four questions honestly — and in LoopKit each answer is a small, swappable, tested object in the kernel."
        >
          <ol className="story">
            {CONCEPTS.map((c, i) => {
              const I = c.icon;
              return (
                <Reveal as="li" className="story-step" delay={i * 0.05} key={c.title}>
                  <div className="story-rail">
                    <span className="story-num">{String(i + 1).padStart(2, "0")}</span>
                  </div>
                  <div className="story-main">
                    <p className="story-q">
                      <span className="story-tag">{c.tag}</span>
                      {c.question}
                    </p>
                    <h3 className="story-title">
                      <span className="story-ic"><I /></span>
                      {c.title}
                    </h3>
                    <p className="story-body">{c.body}</p>
                    <code className="story-sig">{c.sig}</code>
                  </div>
                </Reveal>
              );
            })}
          </ol>
        </Section>

        <Section
          id="architecture"
          eyebrow="how it fits"
          title="Architecture"
          note="Four layers over one seam. The kernel emits; everything else consumes."
        >
          <Reveal><LoopDraw /></Reveal>
          <Reveal delay={0.05}><Diagrams /></Reveal>
        </Section>

        <Section
          id="evals"
          eyebrow="the proof"
          title="Measured, not asserted"
          note="A deterministic harness grades task success with independent checkers — never the loop's own self-report."
        >
          <Reveal><EvalChart /></Reveal>
        </Section>

        <Section
          id="thin"
          eyebrow="the payoff"
          title="How thin is an agent?"
          note="Once the runtime exists, a real agent is just tools + policies — and the thing you enforce is the thing you measure."
        >
          <Reveal className="snippet-wrap">
            <div className="snippet-head">
              <Icon.code /> <span>a11y_auditor.py</span>
              <span className="snippet-hint">one predicate · used twice · never diverges</span>
            </div>
            <pre className="snippet"><code>{AGENT_SNIPPET}</code></pre>
          </Reveal>
        </Section>
      </main>

      <footer className="foot">
        <div className="foot-inner">
          <div className="foot-brand">
            <Icon.loop />
            <span>LoopKit</span>
          </div>
          <nav className="foot-links">
            <a href={REPO} target="_blank" rel="noreferrer"><Icon.github /> Repository</a>
            <a href={`${REPO}#readme`} target="_blank" rel="noreferrer">Docs</a>
            <a href={CONSOLE_HREF}>Observe console</a>
          </nav>
          <p className="foot-note">
            Built as a staff-level study in agent loop engineering. Bring your own
            model — keep the loop.
          </p>
        </div>
      </footer>
    </div>
  );
}

function TopBar() {
  return (
    <div className="topbar">
      <a className="tb-brand" href="./showcase.html">
        <Icon.loop /> <span>LoopKit</span>
      </a>
      <nav className="tb-nav">
        <a href="#replay">Replay</a>
        <a href="#concepts">Concepts</a>
        <a href="#architecture">Architecture</a>
        <a href="#evals">Evals</a>
        <a href="#thin">Code</a>
      </nav>
      <a className="tb-cta" href={REPO} target="_blank" rel="noreferrer">
        <Icon.github /> GitHub
      </a>
    </div>
  );
}

function Section({
  id,
  eyebrow,
  title,
  note,
  children,
}: {
  id: string;
  eyebrow: string;
  title: string;
  note: string;
  children: React.ReactNode;
}) {
  return (
    <section className="section" id={id}>
      <Reveal className="section-head">
        <p className="eyebrow small">{eyebrow}</p>
        <h2>{title}</h2>
        <p className="section-note">{note}</p>
      </Reveal>
      {children}
    </section>
  );
}
