import { useEffect, useState } from "react";
import { Icon } from "./Icon";

// The measured payoff, straight from the eval harness output committed at
// dashboard/public/evals.json (written by examples/m4_evals.py). No chart
// library — hand-rolled SVG/CSS bars so the showcase stays dependency-free and
// the numbers are obviously real, not decorative.
const EVALS = "./evals.json";

interface Summary {
  n: number;
  passed: number;
  success_rate: number;
  mean_iters: number;
  mean_tokens: number;
  total_heals: number;
}
interface Case {
  task_id: string;
  arm: "naive" | "self-heal";
  passed: boolean;
  iterations: number;
  heals: number;
}
interface EvalDoc {
  cases: Case[];
  summaries: Record<string, Summary>;
}

export function EvalChart() {
  const [doc, setDoc] = useState<EvalDoc | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    fetch(EVALS)
      .then((r) => {
        if (!r.ok) throw new Error(`${EVALS} -> ${r.status}`);
        return r.json();
      })
      .then((d) => alive && setDoc(d as EvalDoc))
      .catch((e) => alive && setErr(String(e)));
    return () => {
      alive = false;
    };
  }, []);

  if (err) return <p className="muted">Couldn’t load eval results ({err}).</p>;
  if (!doc) return <p className="muted">Loading eval results…</p>;

  const naive = doc.summaries["naive"];
  const heal = doc.summaries["self-heal"];
  const tasks = Array.from(new Set(doc.cases.map((c) => c.task_id)));

  const byKey = (task: string, arm: string) =>
    doc.cases.find((c) => c.task_id === task && c.arm === arm);

  return (
    <div className="eval-block">
      <div className="eval-bars">
        <ArmBar label="Naive loop" cls="naive" summary={naive} />
        <ArmBar label="Self-healing loop" cls="heal" summary={heal} />
      </div>

      <div className="eval-callout">
        <Icon.spark />
        <p>
          Same tasks, same checkers. The only variable is the loop. Self-healing
          takes <strong>+{(heal.mean_iters - naive.mean_iters).toFixed(1)} mean
          iterations</strong> and{" "}
          <strong>{heal.total_heals} total heals</strong> to turn{" "}
          <strong>{Math.round(naive.success_rate * 100)}%</strong> into{" "}
          <strong>{Math.round(heal.success_rate * 100)}%</strong> real task
          success — graded by an independent checker, never the loop’s own
          self-report.
        </p>
      </div>

      <table className="eval-grid" aria-label="Per-task outcome, naive vs self-healing">
        <thead>
          <tr>
            <th scope="col">Task</th>
            <th scope="col">Naive</th>
            <th scope="col">Self-heal</th>
            <th scope="col">Heals</th>
          </tr>
        </thead>
        <tbody>
          {tasks.map((t) => {
            const n = byKey(t, "naive");
            const h = byKey(t, "self-heal");
            return (
              <tr key={t}>
                <th scope="row"><code>{t}</code></th>
                <td><Outcome ok={!!n?.passed} /></td>
                <td><Outcome ok={!!h?.passed} /></td>
                <td className="num">{h?.heals ?? 0}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function ArmBar({ label, cls, summary }: { label: string; cls: string; summary: Summary }) {
  const pct = Math.round(summary.success_rate * 100);
  return (
    <div className={`arm ${cls}`}>
      <div className="arm-head">
        <span className="arm-label">{label}</span>
        <span className="arm-pct">{pct}%</span>
      </div>
      <div className="arm-track" role="img" aria-label={`${label}: ${pct}% task success (${summary.passed} of ${summary.n})`}>
        <div className="arm-fill" style={{ width: `${pct}%` }} />
      </div>
      <div className="arm-meta">
        {summary.passed}/{summary.n} passed · {summary.mean_iters.toFixed(1)} iters ·{" "}
        {summary.mean_tokens.toFixed(0)} tok · {summary.total_heals} heals
      </div>
    </div>
  );
}

function Outcome({ ok }: { ok: boolean }) {
  return ok ? (
    <span className="outcome pass"><Icon.check /> pass</span>
  ) : (
    <span className="outcome fail">✕ fail</span>
  );
}
