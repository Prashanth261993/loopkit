import type { LoopEvent, IterationView, RunModel } from "../types";

const ICON: Record<string, string> = {
  "run.start": "▶",
  "iteration.start": "↻",
  "model.request": "→",
  "model.response": "🧠",
  "tool.call": "🔧",
  "tool.result": "✓",
  "heal.trigger": "⚠",
  "heal.critique": "🩹",
  "heal.retry": "↺",
  "thrash.detected": "🌀",
  "stop.check": "⏹",
  "run.end": "■",
};

function summarize(ev: LoopEvent): string {
  const d = ev.data;
  switch (ev.type) {
    case "model.response": {
      const call = d.tool_call as { name?: string } | null;
      if (call?.name) return `chose tool "${call.name}"  ·  ${d.tokens_in ?? 0}→${d.tokens_out ?? 0} tok`;
      if (d.final != null) return `final answer  ·  ${d.tokens_in ?? 0}→${d.tokens_out ?? 0} tok`;
      return `${d.tokens_in ?? 0}→${d.tokens_out ?? 0} tok`;
    }
    case "tool.call":
      return `${d.name}(${compactArgs(d.args)})`;
    case "tool.result":
      return d.ok === false
        ? `error: ${truncate(String(d.error ?? "failed"))}`
        : `ok: ${truncate(String(d.output ?? ""))}${d.dry_run ? "  ·  dry-run" : ""}`;
    case "heal.trigger":
      return `trigger: ${d.reason ?? "?"}`;
    case "heal.critique":
      return truncate(String(d.suggestion ?? d.reason ?? "critique"));
    case "heal.retry":
      return `retry #${d.attempt ?? "?"}`;
    case "thrash.detected":
      return `oscillation ×${d.repeats ?? "?"}: ${truncate(String(d.signature ?? ""))}`;
    case "stop.check":
      return `${d.policy ?? "policy"} → ${truncate(String(d.reason ?? d.decision ?? "stop"), 48)}`;
    case "iteration.start":
      return `context: ${d.context_messages ?? "?"} msgs`;
    case "model.request":
      return `${d.messages ?? "?"} msgs · ${d.tools ?? 0} tools`;
    default:
      return "";
  }
}

function compactArgs(args: unknown): string {
  if (!args || typeof args !== "object") return "";
  const parts = Object.entries(args as Record<string, unknown>).map(
    ([k, v]) => `${k}=${truncate(JSON.stringify(v), 22)}`,
  );
  return parts.join(", ");
}

function truncate(s: string, n = 64): string {
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

function EventRow({ ev }: { ev: LoopEvent }) {
  const kind = ev.type.replace(".", "-");
  return (
    <li className={`ev ev-${kind}`}>
      <span className="ev-icon" aria-hidden>
        {ICON[ev.type] ?? "•"}
      </span>
      <span className="ev-type">{ev.type}</span>
      <span className="ev-summary">{summarize(ev)}</span>
      <span className="ev-seq">#{ev.seq}</span>
    </li>
  );
}

function Iteration({ it }: { it: IterationView }) {
  const badges = [
    it.healed ? <span key="h" className="iter-badge badge-heal">healed</span> : null,
    it.thrashed ? <span key="t" className="iter-badge badge-thrash">thrash</span> : null,
  ].filter(Boolean);
  return (
    <section className={`iteration ${it.healed ? "is-healed" : ""} ${it.thrashed ? "is-thrash" : ""}`}>
      <div className="iter-head">
        <span className="iter-n">iteration {it.n}</span>
        {badges}
      </div>
      <ul className="ev-list">
        {it.events.map((ev) => (
          <EventRow key={ev.seq} ev={ev} />
        ))}
      </ul>
    </section>
  );
}

export function Timeline({ model }: { model: RunModel }) {
  if (model.iterations.length === 0) {
    return (
      <div className="timeline empty">
        <p>No iterations yet. Load a run or press play.</p>
      </div>
    );
  }
  return (
    <div className="timeline">
      {model.iterations.map((it) => (
        <Iteration key={it.n} it={it} />
      ))}
    </div>
  );
}
