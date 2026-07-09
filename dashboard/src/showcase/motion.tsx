import { motion, useReducedMotion, useScroll, useSpring } from "motion/react";
import type { ReactNode } from "react";

// Small, reduced-motion-aware wrappers over motion.dev. Everything the showcase
// animates goes through here so the honouring of prefers-reduced-motion lives in
// exactly one place. Durations stay in the 150-320ms band; easing is a gentle
// ease-out. When the user prefers reduced motion, these degrade to plain, fully
// visible markup with no transform/opacity animation at all.

const EASE = [0.22, 0.8, 0.24, 1] as const;

/** Fade + rise as the element scrolls into view. `delay` staggers siblings. */
export function Reveal({
  children,
  delay = 0,
  y = 16,
  className,
  as = "div",
}: {
  children: ReactNode;
  delay?: number;
  y?: number;
  className?: string;
  as?: "div" | "li" | "section" | "article" | "figure" | "header";
}) {
  const reduced = useReducedMotion();
  const M = (motion as any)[as];
  if (reduced) {
    const Tag = as as any;
    return <Tag className={className}>{children}</Tag>;
  }
  return (
    <M
      className={className}
      initial={{ opacity: 0, y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.25, margin: "0px 0px -10% 0px" }}
      transition={{ duration: 0.55, ease: EASE, delay }}
    >
      {children}
    </M>
  );
}

/** A slim accent bar pinned to the top that fills with page scroll progress.
 *  Scroll-driven (follows the user's own scroll), so it stays on even under
 *  prefers-reduced-motion — it isn't autonomous motion. */
export function ScrollProgress() {
  const { scrollYProgress } = useScroll();
  const scaleX = useSpring(scrollYProgress, {
    stiffness: 120,
    damping: 30,
    restDelta: 0.001,
  });
  return <motion.div className="scroll-rail" style={{ scaleX }} aria-hidden="true" />;
}
