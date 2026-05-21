type DistBarsProps = {
  dist: number[];
  label?: string;
};

function color(index: number, total: number): string {
  if (index < Math.ceil(total / 3)) return "var(--danger)";
  if (index < Math.ceil((total * 2) / 3)) return "var(--warning)";
  return "var(--success)";
}

export function DistBars({ dist, label = "Distribuicao de scores" }: DistBarsProps) {
  const max = Math.max(...dist, 1);
  const total = dist.reduce((sum, value) => sum + value, 0);
  const ariaLabel = total === 0 ? `${label}: sem runs com score` : `${label}: ${total} runs com score`;

  return (
    <span className="distbars" role="img" aria-label={ariaLabel}>
      {dist.map((value, index) => (
        <i
          key={`${index}-${value}`}
          aria-hidden="true"
          style={{ height: Math.max(2, Math.round((value / max) * 22)), background: color(index, dist.length) }}
          title={`${value} runs`}
        />
      ))}
    </span>
  );
}
