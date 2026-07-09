// Inline stroke icons for the showcase chrome. SVG, not emoji: crisp at any
// size, inherit `currentColor`, and screen-reader-safe (aria-hidden — the
// meaning always lives in adjacent text). 24x24 viewBox, 1.75 stroke.
import type { ReactNode } from "react";

function svg(children: ReactNode, extra: Record<string, unknown> = {}) {
  return (
    <svg
      className="icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...extra}
    >
      {children}
    </svg>
  );
}

export const Icon = {
  loop: () => svg(<><path d="M4 8a8 8 0 0 1 14-3l2 2" /><path d="M20 5v4h-4" /><path d="M20 16a8 8 0 0 1-14 3l-2-2" /><path d="M4 19v-4h4" /></>),
  stop: () => svg(<rect x="5" y="5" width="14" height="14" rx="2" />),
  heal: () => svg(<><path d="M12 21s-7-4.35-7-10a4 4 0 0 1 7-2.65A4 4 0 0 1 19 11c0 5.65-7 10-7 10Z" /><path d="M9 12h6" /><path d="M12 9v6" /></>),
  thrash: () => svg(<><path d="M3 12a9 9 0 1 1 3 6.7" /><path d="M3 21v-4h4" /></>),
  eye: () => svg(<><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z" /><circle cx="12" cy="12" r="3" /></>),
  chart: () => svg(<><path d="M4 20V4" /><path d="M4 20h16" /><rect x="7" y="12" width="3" height="5" /><rect x="13" y="8" width="3" height="9" /></>),
  code: () => svg(<><path d="m9 8-4 4 4 4" /><path d="m15 8 4 4-4 4" /></>),
  layers: () => svg(<><path d="M12 3 3 8l9 5 9-5-9-5Z" /><path d="m3 13 9 5 9-5" /><path d="m3 18 9 5 9-5" opacity="0.55" /></>),
  github: () => svg(<path d="M9 19c-4.3 1.4-4.3-2.5-6-3m12 5v-3.5c0-1 .1-1.4-.5-2 2.8-.3 5.5-1.4 5.5-6a4.6 4.6 0 0 0-1.3-3.2 4.2 4.2 0 0 0-.1-3.2s-1.1-.3-3.5 1.3a12 12 0 0 0-6.2 0C6.5 2.8 5.4 3.1 5.4 3.1a4.2 4.2 0 0 0-.1 3.2A4.6 4.6 0 0 0 4 9.5c0 4.6 2.7 5.7 5.5 6-.6.6-.6 1.2-.5 2V21" />),
  arrow: () => svg(<><path d="M5 12h14" /><path d="m13 6 6 6-6 6" /></>),
  spark: () => svg(<path d="M12 3v4m0 10v4m9-9h-4M7 12H3m14.5-5.5-2.8 2.8M9.3 14.7l-2.8 2.8m11 0-2.8-2.8M9.3 9.3 6.5 6.5" />),
  check: () => svg(<path d="m5 13 4 4L19 7" />),
  play: () => svg(<path d="M7 5v14l11-7z" fill="currentColor" stroke="none" />),
};
