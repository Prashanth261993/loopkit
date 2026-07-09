import { useState } from "react";
import { Lightbox } from "./Lightbox";

// Architecture-diagram slot. Ships with hand-drawn inline-SVG fallbacks so the
// showcase is complete today; when the Excalidraw exports land in
// public/diagrams/, the <img> takes over automatically and the fallback simply
// never renders. No code change needed to upgrade the art — just drop the files.
interface Slot {
  src: string;
  title: string;
  caption: string;
  fallback: () => JSX.Element;
}

const SLOTS: Slot[] = [
  {
    src: "./diagrams/layers.svg",
    title: "Four layers, one seam",
    caption:
      "The kernel emits a versioned event stream; everything above consumes it. The dashboard and the eval harness read the same events, so what you measure is what you saw.",
    fallback: LayersFallback,
  },
  {
    src: "./diagrams/iteration-contract.svg",
    title: "The iteration contract",
    caption:
      "One turn of the loop: build context → call model → parse → act → maybe heal → charge governor → check stop. Every arrow is an event on the wire.",
    fallback: IterationFallback,
  },
  {
    src: "./diagrams/event-seam.svg",
    title: "One stream, two readers",
    caption:
      "Each event is written once and fanned out drop-oldest to a JSONL file (replay, CI, evals) and a live SSE feed (dashboard). Observability can never back-pressure the loop.",
    fallback: SeamFallback,
  },
];

export function Diagrams() {
  const [zoom, setZoom] = useState<{ src: string; alt: string } | null>(null);
  return (
    <div className="diagram-grid">
      {SLOTS.map((s) => (
        <DiagramCard key={s.src} slot={s} onZoom={setZoom} />
      ))}
      {zoom && <Lightbox src={zoom.src} alt={zoom.alt} onClose={() => setZoom(null)} />}
    </div>
  );
}

function DiagramCard({
  slot,
  onZoom,
}: {
  slot: Slot;
  onZoom: (z: { src: string; alt: string }) => void;
}) {
  const [failed, setFailed] = useState(false);
  const Fallback = slot.fallback;
  return (
    <figure className="diagram-card">
      <div className="diagram-frame">
        {failed ? (
          <Fallback />
        ) : (
          <button
            type="button"
            className="diagram-zoom"
            aria-label={`Zoom: ${slot.title}`}
            onClick={() => onZoom({ src: slot.src, alt: slot.title })}
          >
            <img
              src={slot.src}
              alt={slot.title}
              loading="lazy"
              onError={() => setFailed(true)}
            />
            <span className="diagram-zoom-hint" aria-hidden="true">⤢ click to zoom</span>
          </button>
        )}
      </div>
      <figcaption>
        <strong>{slot.title}</strong>
        <span>{slot.caption}</span>
      </figcaption>
    </figure>
  );
}

// ---- inline SVG fallbacks (theme-token colours via CSS vars) ---------------

function box(x: number, y: number, w: number, h: number, label: string, cls: string) {
  return (
    <g className={cls}>
      <rect x={x} y={y} width={w} height={h} rx="7" />
      <text x={x + w / 2} y={y + h / 2 + 4} textAnchor="middle">
        {label}
      </text>
    </g>
  );
}

function LayersFallback() {
  return (
    <svg className="fallback-svg" viewBox="0 0 340 210" role="img" aria-label="Four-layer architecture diagram">
      {box(70, 12, 200, 32, "dashboard", "d-node d-accent")}
      {box(50, 60, 240, 32, "loopkit-agents", "d-node")}
      {box(50, 108, 240, 32, "loopkit-tools", "d-node")}
      {box(30, 156, 280, 40, "loopkit  (kernel · events · evals)", "d-node d-base")}
      <g className="d-edge">
        <line x1="170" y1="44" x2="170" y2="60" />
        <line x1="170" y1="92" x2="170" y2="108" />
        <line x1="170" y1="140" x2="170" y2="156" />
      </g>
    </svg>
  );
}

function IterationFallback() {
  const steps = ["context", "model", "parse", "act", "heal?", "stop?"];
  return (
    <svg className="fallback-svg" viewBox="0 0 340 210" role="img" aria-label="Iteration contract flow">
      {steps.map((s, i) => {
        const cx = 55 + (i % 3) * 110;
        const cy = 55 + Math.floor(i / 3) * 90;
        const heal = s === "heal?";
        return (
          <g key={s} className={`d-node ${heal ? "d-heal" : ""}`}>
            <rect x={cx - 42} y={cy - 20} width="84" height="40" rx="7" />
            <text x={cx} y={cy + 4} textAnchor="middle">{s}</text>
          </g>
        );
      })}
      <g className="d-edge">
        <line x1="97" y1="55" x2="123" y2="55" />
        <line x1="207" y1="55" x2="233" y2="55" />
        <line x1="275" y1="75" x2="275" y2="120" />
        <line x1="243" y1="145" x2="207" y2="145" />
        <line x1="133" y1="145" x2="97" y2="145" />
      </g>
    </svg>
  );
}

function SeamFallback() {
  return (
    <svg className="fallback-svg" viewBox="0 0 340 210" role="img" aria-label="Event seam fan-out">
      {box(120, 12, 100, 36, "kernel", "d-node d-base")}
      {box(30, 130, 120, 40, "JSONL file", "d-node")}
      {box(190, 130, 120, 40, "live SSE", "d-node d-accent")}
      {box(120, 74, 100, 30, "BroadcastHub", "d-node d-heal")}
      <g className="d-edge">
        <line x1="170" y1="48" x2="170" y2="74" />
        <line x1="140" y1="104" x2="90" y2="130" />
        <line x1="200" y1="104" x2="250" y2="130" />
      </g>
    </svg>
  );
}
