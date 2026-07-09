import { useEffect, useRef, useState } from "react";
import type { LoopEvent, RunModel } from "../types";
import { parseJsonl, reduceRun } from "../model";
import { ReplayPlayer } from "../sources";
import { RunHeader } from "../components/RunHeader";
import { Timeline } from "../components/Timeline";
import { Icon } from "./Icon";

// The hero centrepiece: a real recorded agent run (the a11y-auditor healing an
// inaccessible <img> it first emitted) replayed entirely in the browser from a
// static JSONL file — zero backend. It reuses the exact same reduceRun/Timeline
// the live observe console uses, so what a visitor watches here is byte-for-byte
// what an operator would have seen live. That is the whole thesis made physical:
// one event stream, two readers, no divergence.
const FIXTURE = "./a11y_showcase.jsonl";

function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
  );
}

export function ReplayEmbed() {
  const [events, setEvents] = useState<LoopEvent[]>([]);
  const [revealed, setRevealed] = useState<LoopEvent[]>([]);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1.5);
  const [err, setErr] = useState<string | null>(null);
  const playerRef = useRef<ReplayPlayer | null>(null);
  const autoLoopRef = useRef(true); // loops until the visitor takes manual control
  const loopTimerRef = useRef<number | null>(null);

  function clearLoopTimer() {
    if (loopTimerRef.current !== null) {
      window.clearTimeout(loopTimerRef.current);
      loopTimerRef.current = null;
    }
  }

  // Load the fixture once.
  useEffect(() => {
    let alive = true;
    fetch(FIXTURE)
      .then((r) => {
        if (!r.ok) throw new Error(`${FIXTURE} -> ${r.status}`);
        return r.text();
      })
      .then((text) => {
        if (!alive) return;
        const evs = parseJsonl(text);
        if (evs.length === 0) throw new Error("no events in fixture");
        setEvents(evs);
      })
      .catch((e) => alive && setErr(String(e)));
    return () => {
      alive = false;
    };
  }, []);

  // Build the player when the fixture arrives. The player owns timing; React
  // state only mirrors it. onDone fires once when a run finishes naturally — we
  // sync the button back to "play" and, if the visitor hasn't taken manual
  // control, loop the run after a short beat so the section stays alive.
  useEffect(() => {
    if (events.length === 0) return;
    const reduced = prefersReducedMotion();
    const onDone = () => {
      setPlaying(false);
      if (autoLoopRef.current) {
        clearLoopTimer();
        loopTimerRef.current = window.setTimeout(() => {
          const p = playerRef.current;
          if (!p) return;
          p.restart();
          p.play();
          setPlaying(true);
        }, 2600);
      }
    };
    const player = new ReplayPlayer(events, setRevealed, speed, onDone, 460);
    playerRef.current = player;
    if (reduced) {
      autoLoopRef.current = false; // no autonomous replay under reduced-motion
      player.toEnd();
    } else {
      player.play();
      setPlaying(true);
    }
    return () => {
      clearLoopTimer();
      player.dispose();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [events]);

  function toggle() {
    const player = playerRef.current;
    if (!player) return;
    clearLoopTimer();
    if (player.playing) {
      autoLoopRef.current = false; // visitor paused — stop auto-looping
      player.pause();
      setPlaying(false);
    } else {
      if (player.finished) player.restart();
      player.play();
      setPlaying(true);
    }
  }

  function restart() {
    const player = playerRef.current;
    if (!player) return;
    clearLoopTimer();
    autoLoopRef.current = true;
    player.restart();
    player.play();
    setPlaying(true);
  }

  function changeSpeed(s: number) {
    setSpeed(s);
    playerRef.current?.setSpeed(s);
  }

  if (err) {
    return (
      <div className="replay-embed error">
        <p>Couldn’t load the replay fixture ({err}).</p>
      </div>
    );
  }

  const model: RunModel = reduceRun(revealed);
  const pct = events.length ? Math.round((revealed.length / events.length) * 100) : 0;

  return (
    <div className="replay-embed">
      <div className="replay-toolbar">
        <div className="replay-controls">
          <button className="rc-btn" onClick={toggle} aria-label={playing ? "Pause replay" : "Play replay"}>
            {playing ? <PauseGlyph /> : <Icon.play />}
            <span>{playing ? "pause" : "play"}</span>
          </button>
          <button className="rc-btn ghost" onClick={restart} aria-label="Restart replay">
            <span>restart</span>
          </button>
          <div className="rc-speeds" role="group" aria-label="Replay speed">
            {[1, 1.5, 3].map((s) => (
              <button
                key={s}
                className={`rc-speed ${speed === s ? "is-active" : ""}`}
                onClick={() => changeSpeed(s)}
                aria-pressed={speed === s}
              >
                {s}×
              </button>
            ))}
          </div>
        </div>
        <div className="replay-progress" aria-hidden="true">
          <div className="rp-track">
            <div className="rp-fill" style={{ width: `${pct}%` }} />
          </div>
          <span className="rp-count">
            {revealed.length}/{events.length} events
          </span>
        </div>
      </div>

      <div className="replay-stage">
        <RunHeader model={model} />
        <Timeline model={model} />
      </div>
    </div>
  );
}

function PauseGlyph() {
  return (
    <svg className="icon" viewBox="0 0 24 24" aria-hidden="true" fill="currentColor">
      <rect x="6" y="5" width="4" height="14" rx="1" />
      <rect x="14" y="5" width="4" height="14" rx="1" />
    </svg>
  );
}
