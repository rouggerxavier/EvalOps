"use client";

import { useEffect, useId, useRef, useState } from "react";

import { clamp } from "./utils";

type AreaChartPoint = {
  label: string;
  value: number;
};

type AreaChartProps = {
  data: AreaChartPoint[];
  color?: string;
  height?: number;
};

export function AreaChart({ data, color = "var(--primary-400)", height = 200 }: AreaChartProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(560);
  // useId keeps server and client markup equal; colons break url(#id) references.
  const gradientId = `area-${useId().replace(/:/g, "")}`;

  useEffect(() => {
    if (!ref.current) return;
    const observer = new ResizeObserver(([entry]) => {
      setWidth(Math.max(220, Math.round(entry.contentRect.width)));
    });
    observer.observe(ref.current);
    return () => observer.disconnect();
  }, []);

  if (data.length === 0) return <div ref={ref} className="chart-empty">Sem dados no periodo</div>;

  const max = Math.max(...data.map((point) => point.value), 0.001);
  const step = data.length > 1 ? width / (data.length - 1) : width;
  const baseY = height - 28;
  const points = data.map((point, index) => {
    const x = index * step;
    const y = baseY - clamp(point.value / max) * (height - 56);
    return [x, y] as const;
  });
  const line = points.map(([x, y], index) => `${index === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`).join(" ");
  const area = `${line} L ${points[points.length - 1][0].toFixed(1)} ${baseY} L 0 ${baseY} Z`;
  const every = Math.max(1, Math.ceil(data.length / 7));

  return (
    <div ref={ref} style={{ width: "100%" }}>
      <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" style={{ width: "100%", height }}>
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.35" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0.25, 0.5, 0.75].map((tick) => {
          const y = 28 + (height - 56) * tick;
          return <line key={tick} x1="0" x2={width} y1={y} y2={y} stroke="var(--border-subtle)" strokeDasharray="2 4" />;
        })}
        <path d={area} fill={`url(#${gradientId})`} />
        <path d={line} fill="none" stroke={color} strokeWidth="1.6" />
        {points.map(([x, y], index) => (index % every === 0 ? <circle key={index} cx={x} cy={y} r="2.4" fill={color} /> : null))}
        {data.map((point, index) =>
          index % every === 0 ? (
            <text key={point.label} x={index * step} y={height - 8} textAnchor="middle" fontSize="10" fill="var(--fg-4)" fontFamily="var(--font-mono)">
              {point.label}
            </text>
          ) : null,
        )}
      </svg>
    </div>
  );
}
