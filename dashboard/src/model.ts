import type { LoopEvent, RunModel, IterationView, RunStatus } from "./types";

// Parse a JSONL blob (one event per line) into typed events. Blank lines and
// malformed lines are skipped rather than throwing — a truncated recording
// should still render everything up to the break.
export function parseJsonl(text: string): LoopEvent[] {
  const out: LoopEvent[] = [];
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (!line) continue;
    try {
      out.push(JSON.parse(line) as LoopEvent);
    } catch {
      // skip malformed line
    }
  }
  return out;
}

function num(v: unknown): number {
  return typeof v === "number" && Number.isFinite(v) ? v : 0;
}

// Fold an ordered event stream into a render-ready RunModel. Pure and
// incremental-friendly: call it with the events revealed so far and it returns a
// consistent snapshot, so live and replay paths share one code path.
export function reduceRun(events: LoopEvent[]): RunModel {
  const model: RunModel = {
    runId: "",
    task: "",
    adapter: "",
    stopPolicy: "",
    tools: [],
    safety: null,
    status: "running",
    stopReason: null,
    iterations: [],
    totals: {
      iterations: 0,
      tokensIn: 0,
      tokensOut: 0,
      cost: 0,
      heals: 0,
      thrashes: 0,
      toolCalls: 0,
      toolErrors: 0,
    },
    tokenSeries: [],
    seen: events.length,
    ended: false,
  };

  const iterMap = new Map<number, IterationView>();
  let cumTokens = 0;

  for (const ev of events) {
    model.runId ||= ev.run_id;

    if (ev.iteration > 0 && ev.type !== "run.start" && ev.type !== "run.end") {
      let iv = iterMap.get(ev.iteration);
      if (!iv) {
        iv = { n: ev.iteration, events: [], healed: false, thrashed: false };
        iterMap.set(ev.iteration, iv);
      }
      iv.events.push(ev);
    }

    switch (ev.type) {
      case "run.start": {
        model.task = String(ev.data.task ?? "");
        model.adapter = String(ev.data.adapter ?? "");
        model.stopPolicy = String(ev.data.stop_policy ?? "");
        model.tools = Array.isArray(ev.data.tools) ? (ev.data.tools as string[]) : [];
        model.safety = (ev.data.safety as Record<string, unknown>) ?? null;
        model.status = "running";
        break;
      }
      case "model.response": {
        const ti = num(ev.data.tokens_in);
        const to = num(ev.data.tokens_out);
        model.totals.tokensIn += ti;
        model.totals.tokensOut += to;
        model.totals.cost += num(ev.data.cost);
        cumTokens += ti + to;
        model.tokenSeries.push({ seq: ev.seq, tokens: cumTokens });
        break;
      }
      case "tool.call": {
        model.totals.toolCalls += 1;
        break;
      }
      case "tool.result": {
        if (ev.data.ok === false) model.totals.toolErrors += 1;
        break;
      }
      case "heal.trigger": {
        model.totals.heals += 1;
        const iv = iterMap.get(ev.iteration);
        if (iv) iv.healed = true;
        break;
      }
      case "thrash.detected": {
        model.totals.thrashes += 1;
        const iv = iterMap.get(ev.iteration);
        if (iv) iv.thrashed = true;
        break;
      }
      case "stop.check": {
        if (ev.data.decision) model.stopReason = String(ev.data.policy ?? "stop");
        break;
      }
      case "run.end": {
        model.status = (String(ev.data.status ?? "failed") as RunStatus) || "failed";
        model.stopReason = String(ev.data.stop_reason ?? ev.data.reason ?? model.stopReason ?? "");
        model.ended = true;
        break;
      }
    }
  }

  model.iterations = [...iterMap.values()].sort((a, b) => a.n - b.n);
  model.totals.iterations = model.iterations.length;
  return model;
}
