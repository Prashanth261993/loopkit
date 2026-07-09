import { useRef } from "react";
import {
  motion,
  useReducedMotion,
  useScroll,
  useTransform,
  type MotionValue,
} from "motion/react";

// The signature scroll animation: the iteration contract drawn as an actual
// loop. As this block scrolls through the viewport, the ring draws itself
// (pathLength 0 -> 1) and the six turn-stages light up in sequence -- the
// thesis ("the loop is the engineering") made kinetic. Honours reduced motion
// by rendering the completed loop statically.

const CX = 300;
const CY = 170;
const RX = 235;
const RY = 128;

const STEPS = ["context", "model", "parse", "act", "heal?", "stop"] as const;

// Node positions around the ellipse, starting at top, clockwise.
const NODES = STEPS.map((label, i) => {
  const a = -Math.PI / 2 + (i / STEPS.length) * Math.PI * 2;
  return {
    label,
    x: CX + RX * Math.cos(a),
    y: CY + RY * Math.sin(a),
    heal: label === "heal?",
  };
});

// A full ellipse expressed as two arcs, so motion can animate its pathLength.
const RING = `M ${CX - RX},${CY} a ${RX},${RY} 0 1,0 ${RX * 2},0 a ${RX},${RY} 0 1,0 ${-RX * 2},0`;

export function LoopDraw() {
  const reduced = useReducedMotion();
  const ref = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start end", "center center"],
  });
  const pathLength = useTransform(scrollYProgress, [0.1, 1], [0, 1]);

  return (
    <div className="loopdraw" ref={ref}>
      <svg viewBox="0 0 600 340" role="img" aria-label="The iteration contract, drawn as a loop">
        <defs>
          <linearGradient id="ld-grad" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="var(--accent)" />
            <stop offset="100%" stopColor="var(--accent-2)" />
          </linearGradient>
        </defs>

        {/* faint full ring underneath */}
        <path d={RING} className="ld-track" fill="none" />

        {/* the drawing ring */}
        {reduced ? (
          <path d={RING} className="ld-ring" fill="none" />
        ) : (
          <motion.path d={RING} className="ld-ring" fill="none" style={{ pathLength }} />
        )}

        {NODES.map((n, i) =>
          reduced ? (
            <StaticNode key={n.label} n={n} />
          ) : (
            <LiveNode key={n.label} n={n} index={i} progress={scrollYProgress} />
          ),
        )}
      </svg>
      <p className="loopdraw-cap">
        one turn, six moves — and every arrow is an event on the wire
      </p>
    </div>
  );
}

function nodeMarkup(n: (typeof NODES)[number]) {
  return (
    <>
      <circle cx={n.x} cy={n.y} r="8" className={`ld-dot ${n.heal ? "ld-heal" : ""}`} />
      <text x={n.x} y={n.y - 16} textAnchor="middle" className="ld-label">
        {n.label}
      </text>
    </>
  );
}

function StaticNode({ n }: { n: (typeof NODES)[number] }) {
  return <g className="ld-node">{nodeMarkup(n)}</g>;
}

function LiveNode({
  n,
  index,
  progress,
}: {
  n: (typeof NODES)[number];
  index: number;
  progress: MotionValue<number>;
}) {
  const start = index / STEPS.length;
  const opacity = useTransform(progress, [start - 0.05, start + 0.06], [0.35, 1]);
  const scale = useTransform(progress, [start - 0.05, start + 0.06], [0.7, 1]);
  return (
    <motion.g
      className="ld-node"
      style={{ opacity, scale, transformOrigin: `${n.x}px ${n.y}px` }}
    >
      {nodeMarkup(n)}
    </motion.g>
  );
}
