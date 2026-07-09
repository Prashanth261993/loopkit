import { useCallback, useMemo, useRef, useState } from "react";
import type { LoopEvent, RunModel } from "./types";
import { parseJsonl, reduceRun } from "./model";
import { ReplayPlayer, connectSse, fetchRuns } from "./sources";
import type { ServerRun } from "./sources";
import { SourceBar } from "./components/SourceBar";
import type { Mode, ReplayControls } from "./components/SourceBar";
import { RunHeader } from "./components/RunHeader";
import { Timeline } from "./components/Timeline";

export default function App() {
  const [events, setEvents] = useState<LoopEvent[]>([]);
  const [mode, setMode] = useState<Mode>("idle");
  const [error, setError] = useState<string | null>(null);
  const [serverRuns, setServerRuns] = useState<ServerRun[]>([]);
  const [, setTick] = useState(0);
  const bump = () => setTick((t) => t + 1);

  const playerRef = useRef<ReplayPlayer | null>(null);
  const sseRef = useRef<(() => void) | null>(null);

  const teardown = useCallback(() => {
    playerRef.current?.dispose();
    playerRef.current = null;
    sseRef.current?.();
    sseRef.current = null;
  }, []);

  const startFile = useCallback(
    (all: LoopEvent[]) => {
      teardown();
      setError(null);
      if (all.length === 0) {
        setError("no valid events found in file");
        return;
      }
      setMode("file");
      const player = new ReplayPlayer(
        all,
        (revealed) => {
          setEvents(revealed);
          bump();
        },
        1,
      );
      playerRef.current = player;
      player.play();
      bump();
    },
    [teardown],
  );

  const onLoadSample = useCallback(async () => {
    try {
      teardown();
      setError(null);
      const res = await fetch("./sample.jsonl");
      if (!res.ok) throw new Error(`sample.jsonl -> ${res.status}`);
      startFile(parseJsonl(await res.text()));
    } catch (e) {
      setError(String(e));
    }
  }, [startFile, teardown]);

  const onUploadFile = useCallback(
    (file: File) => {
      const reader = new FileReader();
      reader.onload = () => startFile(parseJsonl(String(reader.result ?? "")));
      reader.onerror = () => setError("could not read file");
      reader.readAsText(file);
    },
    [startFile],
  );

  const startStream = useCallback(
    (path: string, nextMode: Mode) => {
      teardown();
      setError(null);
      setEvents([]);
      setMode(nextMode);
      const collected: LoopEvent[] = [];
      sseRef.current = connectSse(
        path,
        (ev) => {
          collected.push(ev);
          setEvents([...collected]);
        },
        () => bump(),
        (err) => setError(err),
      );
      bump();
    },
    [teardown],
  );

  const onConnectLive = useCallback(() => startStream("/events", "live"), [startStream]);

  const onRefreshRuns = useCallback(async () => {
    try {
      setServerRuns(await fetchRuns());
      setError(null);
    } catch (e) {
      setError(`${e} — is the observe server running?`);
    }
  }, []);

  const onReplayServer = useCallback(
    (name: string) => startStream(`/api/replay?run=${encodeURIComponent(name)}&speed=1`, "server"),
    [startStream],
  );

  // Replay transport controls (file mode only).
  const player = playerRef.current;
  const withPlayer = (fn: (p: ReplayPlayer) => void) => () => {
    if (player) {
      fn(player);
      bump();
    }
  };
  const onPlayPause = withPlayer((p) => (p.playing ? p.pause() : p.play()));
  const onStep = withPlayer((p) => p.step());
  const onRestart = withPlayer((p) => {
    p.restart();
    p.play();
  });
  const onToEnd = withPlayer((p) => p.toEnd());
  const onSpeed = (s: number) => {
    if (player) {
      player.setSpeed(s);
      bump();
    }
  };

  const replay: ReplayControls | null =
    mode === "file" && player
      ? {
          playing: player.playing,
          position: player.position,
          total: player.total,
          speed: player.speed,
          finished: player.finished,
        }
      : null;

  const model: RunModel = useMemo(() => reduceRun(events), [events]);
  const hasRun = events.length > 0;

  return (
    <div className="app">
      <SourceBar
        mode={mode}
        error={error}
        serverRuns={serverRuns}
        replay={replay}
        onLoadSample={onLoadSample}
        onUploadFile={onUploadFile}
        onConnectLive={onConnectLive}
        onRefreshRuns={onRefreshRuns}
        onReplayServer={onReplayServer}
        onPlayPause={onPlayPause}
        onStep={onStep}
        onRestart={onRestart}
        onToEnd={onToEnd}
        onSpeed={onSpeed}
      />

      <main className="main">
        {hasRun ? (
          <>
            <RunHeader model={model} />
            <Timeline model={model} />
          </>
        ) : (
          <Welcome onLoadSample={onLoadSample} />
        )}
      </main>
    </div>
  );
}

function Welcome({ onLoadSample }: { onLoadSample: () => void }) {
  return (
    <div className="welcome">
      <h1>Watch an agent think — and heal itself.</h1>
      <p>
        LoopKit emits one versioned event stream per run. This console replays that stream from a
        static <code>.jsonl</code> file (zero backend) or tails a live run over SSE. Same schema,
        two transports.
      </p>
      <button className="btn btn-primary" onClick={onLoadSample}>
        ★ Play the sample run
      </button>
      <p className="welcome-hint">
        …or upload your own <code>artifacts/*.jsonl</code>, or connect to a running{" "}
        <code>loopkit.observe</code> server.
      </p>
    </div>
  );
}
