interface Props {
  series: { seq: number; tokens: number }[];
}

// A dependency-free cumulative-token sparkline. Cost is proportional to tokens,
// so this doubles as the "spend curve" — the shape that makes budget pressure
// legible at a glance.
export function TokenChart({ series }: Props) {
  const w = 520;
  const h = 90;
  const pad = 6;

  if (series.length < 2) {
    return (
      <div className="chart empty">
        <span>token curve appears once the run produces model responses…</span>
      </div>
    );
  }

  const maxTokens = series[series.length - 1].tokens || 1;
  const n = series.length;
  const x = (i: number) => pad + (i / (n - 1)) * (w - 2 * pad);
  const y = (t: number) => h - pad - (t / maxTokens) * (h - 2 * pad);

  const line = series.map((p, i) => `${x(i).toFixed(1)},${y(p.tokens).toFixed(1)}`).join(" ");
  const area = `${pad},${h - pad} ${line} ${(w - pad).toFixed(1)},${h - pad}`;

  return (
    <div className="chart">
      <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" role="img" aria-label="cumulative tokens">
        <polygon points={area} className="spark-area" />
        <polyline points={line} className="spark-line" />
      </svg>
      <div className="chart-caption">
        <span>cumulative tokens</span>
        <strong>{maxTokens.toLocaleString()}</strong>
      </div>
    </div>
  );
}
