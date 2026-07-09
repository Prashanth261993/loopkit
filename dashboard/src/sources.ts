import type { LoopEvent } from "./types";

// Pacing bounds mirror the Python replay server so a file replay in the browser
// looks identical to a server-paced SSE replay.
const MIN_DELAY = 20;
const MAX_DELAY = 750;

// A deterministic replay player. Holds a full event array and reveals it one
// event at a time, paced by the recorded `ts` deltas (scaled by speed). This is
// what makes a static, backend-free JSONL file *feel* like a live run — the
// whole point of the M6 showcase.
export class ReplayPlayer {
  private all: LoopEvent[];
  private cursor = 0;
  private timer: number | null = null;
  private _speed: number;
  private onReveal: (revealed: LoopEvent[]) => void;

  playing = false;

  constructor(
    all: LoopEvent[],
    onReveal: (revealed: LoopEvent[]) => void,
    speed = 1,
  ) {
    this.all = all;
    this.onReveal = onReveal;
    this._speed = speed;
    this.emit();
  }

  get total(): number {
    return this.all.length;
  }
  get position(): number {
    return this.cursor;
  }
  get speed(): number {
    return this._speed;
  }
  get finished(): boolean {
    return this.cursor >= this.all.length;
  }

  setSpeed(speed: number): void {
    this._speed = speed;
    if (this.playing) {
      this.pause();
      this.play();
    }
  }

  play(): void {
    if (this.finished) return;
    this.playing = true;
    this.scheduleNext();
  }

  pause(): void {
    this.playing = false;
    if (this.timer !== null) {
      window.clearTimeout(this.timer);
      this.timer = null;
    }
  }

  step(): void {
    this.pause();
    if (this.finished) return;
    this.cursor += 1;
    this.emit();
  }

  restart(): void {
    this.pause();
    this.cursor = 0;
    this.emit();
  }

  toEnd(): void {
    this.pause();
    this.cursor = this.all.length;
    this.emit();
  }

  dispose(): void {
    this.pause();
  }

  private scheduleNext(): void {
    if (!this.playing || this.finished) {
      this.playing = false;
      return;
    }
    const prev = this.all[this.cursor - 1];
    const next = this.all[this.cursor];
    let delay = 0;
    if (prev && next) {
      delay = ((next.ts - prev.ts) * 1000) / this._speed;
      delay = Math.max(MIN_DELAY, Math.min(MAX_DELAY, delay));
    } else {
      delay = MIN_DELAY;
    }
    this.timer = window.setTimeout(() => {
      this.cursor += 1;
      this.emit();
      this.scheduleNext();
    }, delay);
  }

  private emit(): void {
    this.onReveal(this.all.slice(0, this.cursor));
  }
}

// Connect to the observe server's SSE endpoint. `path` is either "/events"
// (live in-process feed) or "/api/replay?run=NAME" (server-paced replay).
// Returns a disposer.
export function connectSse(
  path: string,
  onEvent: (ev: LoopEvent) => void,
  onEnd: () => void,
  onError: (err: string) => void,
): () => void {
  const es = new EventSource(path);
  es.onmessage = (e) => {
    try {
      onEvent(JSON.parse(e.data) as LoopEvent);
    } catch {
      // ignore malformed frame
    }
  };
  es.addEventListener("end", () => {
    es.close();
    onEnd();
  });
  es.onerror = () => {
    // EventSource auto-reconnects; surface a hint but don't spam.
    onError("stream error (is the observe server running?)");
  };
  return () => es.close();
}

export interface ServerRun {
  name: string;
  bytes: number;
}

export async function fetchRuns(): Promise<ServerRun[]> {
  const res = await fetch("/api/runs");
  if (!res.ok) throw new Error(`/api/runs -> ${res.status}`);
  const body = (await res.json()) as { runs: ServerRun[] };
  return body.runs ?? [];
}
