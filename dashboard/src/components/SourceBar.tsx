import { useRef } from "react";
import type { ServerRun } from "../sources";

export type Mode = "idle" | "file" | "live" | "server";

export interface ReplayControls {
  playing: boolean;
  position: number;
  total: number;
  speed: number;
  finished: boolean;
}

interface Props {
  mode: Mode;
  error: string | null;
  serverRuns: ServerRun[];
  replay: ReplayControls | null; // present only in file mode
  onLoadSample: () => void;
  onUploadFile: (file: File) => void;
  onConnectLive: () => void;
  onRefreshRuns: () => void;
  onReplayServer: (name: string) => void;
  onPlayPause: () => void;
  onStep: () => void;
  onRestart: () => void;
  onToEnd: () => void;
  onSpeed: (speed: number) => void;
}

const SPEEDS = [0.5, 1, 2, 4, 8];

export function SourceBar(props: Props) {
  const fileInput = useRef<HTMLInputElement>(null);

  return (
    <div className="sourcebar">
      <div className="brand">
        <span className="brand-mark">◴</span>
        <div>
          <div className="brand-name">LoopKit · Observe</div>
          <div className="brand-sub">one event schema · file or live</div>
        </div>
      </div>

      <div className="source-actions">
        <button className="btn" onClick={props.onLoadSample}>
          ★ Sample run
        </button>

        <button className="btn" onClick={() => fileInput.current?.click()}>
          ⬆ Upload .jsonl
        </button>
        <input
          ref={fileInput}
          type="file"
          accept=".jsonl,.json,.txt"
          style={{ display: "none" }}
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) props.onUploadFile(f);
            e.target.value = "";
          }}
        />

        <button className="btn" onClick={props.onConnectLive}>
          ⚡ Live
        </button>

        <div className="server-picker">
          <button className="btn btn-ghost" onClick={props.onRefreshRuns} title="list server runs">
            ⟳
          </button>
          <select
            className="run-select"
            defaultValue=""
            onChange={(e) => {
              if (e.target.value) props.onReplayServer(e.target.value);
            }}
          >
            <option value="" disabled>
              server replay…
            </option>
            {props.serverRuns.map((r) => (
              <option key={r.name} value={r.name}>
                {r.name} ({fmtBytes(r.bytes)})
              </option>
            ))}
          </select>
        </div>

        <span className={`mode-pill mode-${props.mode}`}>{props.mode}</span>
      </div>

      {props.replay && (
        <div className="replay-controls">
          <button className="btn btn-sm" onClick={props.onRestart} title="restart">
            ⏮
          </button>
          <button className="btn btn-sm" onClick={props.onPlayPause}>
            {props.replay.playing ? "⏸ pause" : props.replay.finished ? "↺ replay" : "▶ play"}
          </button>
          <button className="btn btn-sm" onClick={props.onStep} title="step one event">
            ⏭
          </button>
          <button className="btn btn-sm" onClick={props.onToEnd} title="jump to end">
            ⤓ end
          </button>
          <div className="progress">
            <div
              className="progress-fill"
              style={{
                width: `${props.replay.total ? (props.replay.position / props.replay.total) * 100 : 0}%`,
              }}
            />
          </div>
          <span className="progress-label">
            {props.replay.position}/{props.replay.total}
          </span>
          <div className="speeds">
            {SPEEDS.map((s) => (
              <button
                key={s}
                className={`btn btn-chip ${props.replay!.speed === s ? "active" : ""}`}
                onClick={() => props.onSpeed(s)}
              >
                {s}×
              </button>
            ))}
          </div>
        </div>
      )}

      {props.error && <div className="error-bar">{props.error}</div>}
    </div>
  );
}

function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}
