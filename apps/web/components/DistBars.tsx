type DistBarsProps = {
  dist: number[];
  label?: string;
};

function toneForBucket(index: number, total: number): "low" | "mid" | "high" {
  const lowCutoff = Math.ceil(total / 3);
  const highCutoff = Math.ceil((total * 2) / 3);
  if (index < lowCutoff) return "low";
  if (index < highCutoff) return "mid";
  return "high";
}

export function DistBars({ dist, label = "Distribuicao de scores" }: DistBarsProps) {
  const max = Math.max(...dist, 1);
  const total = dist.reduce((sum, value) => sum + value, 0);
  const ariaLabel =
    total === 0 ? `${label}: sem runs com score` : `${label}: ${total} run${total !== 1 ? "s" : ""} com score`;

  return (
    <div className="dist-bars" role="img" aria-label={ariaLabel}>
      {dist.map((value, index) => {
        const heightPx = Math.max(3, Math.round((value / max) * 22));
        const tone = toneForBucket(index, dist.length);
        return (
          <span
            aria-hidden="true"
            className={`dist-bar dist-bar--${tone}`}
            key={`${index}-${value}`}
            style={{ height: heightPx }}
            title={`${value} run${value !== 1 ? "s" : ""}`}
          />
        );
      })}
    </div>
  );
}
