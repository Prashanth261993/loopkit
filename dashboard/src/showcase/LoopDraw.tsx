import { useRef } from "react";
import { motion, useScroll, useTransform, type MotionValue } from "motion/react";

// The signature scroll animation: the iteration contract drawn as an actual
// loop. As this block scrolls through the viewport the ring draws itself
// (pathLength 0 -> 1), the six turn-stages light up in sequence, and directional
// arrowheads confirm the flow -- the thesis ("the loop is the engineering")
// made kinetic. This is scroll-DRIVEN (it follows the user's own scroll), so it
// stays active even under prefers-reduced-motion; only autonomous motion (fades,
// replay autoplay) is gated off elsewhere.

const CX = 300;
const CY = 170;
const RX = 235;
const RY = 128;
const N = 6;

const STEPS = ["context", "model", "parse", "act", "heal?", "stop"] as const;

const nodeAngle = (i: number) => -Math.PI / 2 + (i / N) * Math.PI * 2;

// Node positions around the ellipse, starting at top, clockwise.
const NODES = STEPS.map((label, i) => {
  const a = nodeAngle(i);
  return { label, x: CX + RX * Math.cos(a), y: CY + RY * Math.sin(a), heal: label === "heal?" };
});

// Arrowheads sit at each segment midpoint, rotated to the ellipse tangent so
// they point clockwise — the direction the loop flows.
const ARROWS = STEPS.map((_, i) => {
  const a = nodeAngle(i + 0.5);
  const x = CX + RX * Math.cos(a);
  const y = CY + RY * Math.sin(a);
  const deg = (Math.atan2(RY * Math.cos(a), -RX * Math.sin(a)) * 180) / Math.PI;
  return { x, y, deg, at: (i + 0.5) / N };
});

// A full ellipse expressed as two arcs, so motion can animate its pathLength.
const RING = `M ${CX - RX},${CY} a ${RX},${RY} 0 1,0 ${RX * 2},0 a ${RX},${RY} 0 1,0 ${-RX * 2},0`;

export function LoopDraw() {
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
        <motion.path d={RING} className="ld-ring" fill="none" style={{ pathLength }} />

        {/* directional arrowheads */}
        {ARROWS.map((a, i) => (
          <LiveArrow key={i} a={a} progress={scrollYProgress} />
        ))}

        {NODES.map((n, i) => (
          <LiveNode key={n.label} n={n} index={i} progress={scrollYProgress} />
        ))}
      </svg>
      <p className="loopdraw-cap">
        one turn, six moves — and every arrow is an event on the wire
      </p>
    </div>
  );
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
  const start = index / N;
  const opacity = useTransform(progress, [start - 0.05, start + 0.06], [0.35, 1]);
  const scale = useTransform(progress, [start - 0.05, start + 0.06], [0.7, 1]);
  return (
    <motion.g className="ld-node" style={{ opacity, scale, transformOrigin: `${n.x}px ${n.y}px` }}>
      <circle cx={n.x} cy={n.y} r="8" className={`ld-dot ${n.heal ? "ld-heal" : ""}`} />
      <text x={n.x} y={n.y - 16} textAnchor="middle" className="ld-label">
        {n.label}
      </text>
    </motion.g>
  );
}

function LiveArrow({ a, progress }: { a: (typeof ARROWS)[number]; progress: MotionValue<number> }) {
  const opacity = useTransform(progress, [a.at - 0.04, a.at + 0.04], [0, 1]);
  return (
    <motion.g
      className="ld-arrow"
      style={{ opacity }}
      transform={`translate(${a.x} ${a.y}) rotate(${a.deg})`}
    >
      <polygon points="-5,-5 7,0 -5,5" />
    </motion.g>
  );
}
