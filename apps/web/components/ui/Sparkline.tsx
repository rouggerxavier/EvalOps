import { clamp } from "./utils";

type SparklineProps = {
  points: number[];
  color?: string;
  width?: number;
  height?: number;
  id?: string;
};

export function Sparkline({
  points,
  color = "var(--primary-400)",
  width = 90,
  height = 28,
  id = "spark",
}: SparklineProps) {
  if (points.length < 2) return null;

  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = max - min || 1;
  const step = width / (points.length - 1);
  const path = points
    .map((value, index) => {
      const x = index * step;
      const y = height - clamp((value - min) / range) * (height - 4) - 2;
      return `${index === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(" ");
  const fillPath = `${path} L ${width} ${height} L 0 ${height} Z`;
  const gradientId = `spark-${id.replace(/[^a-zA-Z0-9_-]/g, "-")}`;

  return (
    <svg className="metric__spark" width={width} height={height} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-hidden="true">
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.35" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={fillPath} fill={`url(#${gradientId})`} />
      <path d={path} fill="none" stroke={color} strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
