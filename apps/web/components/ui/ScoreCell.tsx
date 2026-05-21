import { clamp } from "./utils";

type ScoreCellProps = {
  value: number | null | undefined;
};

export function ScoreCell({ value }: ScoreCellProps) {
  if (value === null || value === undefined) return <span className="faint mono">-</span>;
  const tone = value >= 0.85 ? "ok" : value >= 0.7 ? "warn" : "err";
  return (
    <span className={`score score--${tone}`}>
      <span className="score__bar">
        <i style={{ width: `${clamp(value) * 100}%` }} />
      </span>
      {value.toFixed(2)}
    </span>
  );
}
