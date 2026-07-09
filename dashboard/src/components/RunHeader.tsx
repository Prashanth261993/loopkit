import type { RunModel } from "../types";
import { TokenChart } from "./TokenChart";

const STATUS_LABEL: Record<string, string> = {
  success: "success",
  failed: "failed",
  max_iters: "max iterations",
  budget_exceeded: "budget exceeded",
  stalled: "stalled",
  thrashing: "thrashing",
  running: "running…",
};

interface Props {
  model: RunModel;
}

export function RunHeader({ model }: Props) {
  const t = model.totals;
  return (
    <header className="run-header">
      <div className="run-title">
        <div className="run-task">
          <span className="eyebrow">task</span>
          <h1>{model.task || "—"}</h1>
        </div>
        <span className={`status status-${model.status}`}>
          {STATUS_LABEL[model.status] ?? model.status}
        </span>
      </div>

      <div className="stat-grid">
        <Stat label="iterations" value={t.iterations} />
        <Stat label="tokens in" value={t.tokensIn.toLocaleString()} />
        <Stat label="tokens out" value={t.tokensOut.toLocaleString()} />
        <Stat label="cost" value={`$${t.cost.toFixed(4)}`} />
        <Stat label="tool calls" value={t.toolCalls} />
        <Stat label="tool errors" value={t.toolErrors} accent={t.toolErrors ? "warn" : undefined} />
        <Stat label="heals" value={t.heals} accent={t.heals ? "heal" : undefined} />
        <Stat label="thrash" value={t.thrashes} accent={t.thrashes ? "warn" : undefined} />
      </div>

      <TokenChart series={model.tokenSeries} />

      <div className="meta-row">
        {model.adapter && <span className="chip">adapter · {model.adapter}</span>}
        {model.stopPolicy && <span className="chip">stop · {model.stopPolicy}</span>}
        {model.stopReason && <span className="chip chip-stop">stopped by · {model.stopReason}</span>}
        {model.safety && (
          <span className="chip chip-safety">
            safety · {String((model.safety as Record<string, unknown>).mode ?? "on")}
          </span>
        )}
        {model.tools.map((tool) => (
          <span key={tool} className="chip chip-tool">
            🔧 {tool}
          </span>
        ))}
      </div>
    </header>
  );
}

function Stat({ label, value, accent }: { label: string; value: string | number; accent?: string }) {
  return (
    <div className={`stat ${accent ? `stat-${accent}` : ""}`}>
      <span className="stat-value">{value}</span>
      <span className="stat-label">{label}</span>
    </div>
  );
}
