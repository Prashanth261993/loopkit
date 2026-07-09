import { useState } from "react";
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

type Msg = { role?: string; name?: string; preview?: string; chars?: number };

function hasDetail(ev: LoopEvent): boolean {
  const d = ev.data ?? {};
  switch (ev.type) {
    case "model.request":
      return Array.isArray(d.message_previews) || Array.isArray(d.tool_names);
    case "model.response":
      return d.thought != null || d.tool_call != null || d.final != null;
    case "tool.call":
      return d.args != null;
    case "tool.result":
      return d.output != null || d.error != null;
    case "iteration.start":
      return d.context_strategy != null;
    case "heal.critique":
    case "heal.trigger":
    case "stop.check":
      return true;
    default:
      return d != null && Object.keys(d).length > 0;
  }
}

function pretty(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function Details({ ev }: { ev: LoopEvent }) {
  const d = ev.data ?? {};
  switch (ev.type) {
    case "model.request": {
      const msgs = (d.message_previews as Msg[] | undefined) ?? [];
      const tools = (d.tool_names as string[] | undefined) ?? [];
      return (
        <div className="ev-details">
          {msgs.length > 0 && (
            <>
              <div className="ev-details-label">messages sent ({msgs.length})</div>
              <ul className="ev-msgs">
                {msgs.map((m, i) => (
                  <li key={i} className="ev-msg">
                    <span className={`ev-msg-role role-${m.role ?? "?"}`}>
                      {m.role}
                      {m.name ? `/${m.name}` : ""}
                    </span>
                    <span className="ev-msg-preview">{m.preview}</span>
                    {m.chars != null && <span className="ev-msg-chars">{m.chars} ch</span>}
                  </li>
                ))}
              </ul>
            </>
          )}
          {tools.length > 0 && (
            <>
              <div className="ev-details-label">tools available ({tools.length})</div>
              <div className="ev-tools">
                {tools.map((t) => (
                  <span key={t} className="ev-tool-chip">
                    {t}
                  </span>
                ))}
              </div>
            </>
          )}
        </div>
      );
    }
    case "model.response": {
      const call = d.tool_call as { name?: string; args?: unknown } | null;
      return (
        <div className="ev-details">
          {d.thought != null && (
            <>
              <div className="ev-details-label">thought</div>
              <pre className="ev-pre">{String(d.thought)}</pre>
            </>
          )}
          {call?.name && (
            <>
              <div className="ev-details-label">tool call → {call.name}</div>
              <pre className="ev-pre">{pretty(call.args)}</pre>
            </>
          )}
          {d.final != null && (
            <>
              <div className="ev-details-label">final answer</div>
              <pre className="ev-pre">{String(d.final)}</pre>
            </>
          )}
        </div>
      );
    }
    case "tool.call":
      return (
        <div className="ev-details">
          <div className="ev-details-label">args</div>
          <pre className="ev-pre">{pretty(d.args)}</pre>
        </div>
      );
    case "tool.result":
      return (
        <div className="ev-details">
          <div className="ev-details-label">{d.ok === false ? "error" : "output"}</div>
          <pre className="ev-pre">{String(d.error ?? d.output ?? "")}</pre>
        </div>
      );
    case "iteration.start":
      return (
        <div className="ev-details">
          <div className="ev-details-label">context</div>
          <pre className="ev-pre">{pretty(d)}</pre>
        </div>
      );
    default:
      return (
        <div className="ev-details">
          <pre className="ev-pre">{pretty(d)}</pre>
        </div>
      );
  }
}

function EventRow({ ev }: { ev: LoopEvent }) {
  const [open, setOpen] = useState(false);
  const kind = ev.type.replace(".", "-");
  const expandable = hasDetail(ev);
  return (
    <li className={`ev-item ${open ? "is-open" : ""}`}>
      <div
        className={`ev ev-${kind} ${expandable ? "is-expandable" : ""}`}
        onClick={expandable ? () => setOpen((o) => !o) : undefined}
        role={expandable ? "button" : undefined}
        tabIndex={expandable ? 0 : undefined}
        onKeyDown={
          expandable
            ? (e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  setOpen((o) => !o);
                }
              }
            : undefined
        }
        aria-expanded={expandable ? open : undefined}
      >
        <span className="ev-icon" aria-hidden>
          {expandable ? (open ? "▾" : "▸") : ICON[ev.type] ?? "•"}
        </span>
        <span className="ev-type">{ev.type}</span>
        <span className="ev-summary">{summarize(ev)}</span>
        <span className="ev-seq">#{ev.seq}</span>
      </div>
      {open && expandable && <Details ev={ev} />}
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
