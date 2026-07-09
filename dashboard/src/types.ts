// The TypeScript view of the LoopKit event schema. This mirrors
// `packages/loopkit/src/loopkit/events.py` — the two evolve independently as long
// as they agree on this envelope. `schema_version` is the contract; if the major
// version ever changes, this file is where we branch.

export const SUPPORTED_SCHEMA = "0.1.0";

export type EventType =
  | "run.start"
  | "iteration.start"
  | "model.request"
  | "model.response"
  | "tool.call"
  | "tool.result"
  | "heal.trigger"
  | "heal.critique"
  | "heal.retry"
  | "thrash.detected"
  | "stop.check"
  | "run.end";

// The common envelope stamped on every event.
export interface LoopEvent {
  schema_version: string;
  run_id: string;
  seq: number;
  ts: number;
  iteration: number;
  type: EventType;
  data: Record<string, unknown>;
}

export type RunStatus =
  | "success"
  | "failed"
  | "max_iters"
  | "budget_exceeded"
  | "stalled"
  | "thrashing"
  | "running";

// A folded, render-ready view of a whole run, derived from the raw event stream
// by `reduceRun` in model.ts.
export interface IterationView {
  n: number;
  events: LoopEvent[];
  healed: boolean;
  thrashed: boolean;
}

export interface RunModel {
  runId: string;
  task: string;
  adapter: string;
  stopPolicy: string;
  tools: string[];
  safety: Record<string, unknown> | null;
  status: RunStatus;
  stopReason: string | null;
  iterations: IterationView[];
  totals: {
    iterations: number;
    tokensIn: number;
    tokensOut: number;
    cost: number;
    heals: number;
    thrashes: number;
    toolCalls: number;
    toolErrors: number;
  };
  // cumulative (seq, tokens) points for the sparkline
  tokenSeries: { seq: number; tokens: number }[];
  seen: number;
  ended: boolean;
}
