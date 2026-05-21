import type { ReactNode } from "react";

import { Sparkline } from "./Sparkline";
import { cn } from "./utils";

type MetricProps = {
  label: ReactNode;
  value: ReactNode;
  unit?: ReactNode;
  icon?: ReactNode;
  delta?: ReactNode;
  deltaTone?: "up" | "down" | "neutral";
  spark?: number[];
  sparkColor?: string;
  className?: string;
};

export function Metric({
  label,
  value,
  unit,
  icon,
  delta,
  deltaTone = "neutral",
  spark,
  sparkColor,
  className,
}: MetricProps) {
  return (
    <div className={cn("metric", className)}>
      <div className="metric__label">
        {icon}
        {label}
      </div>
      <div className="metric__value">
        {value}
        {unit ? <span className="metric__unit">{unit}</span> : null}
      </div>
      {delta ? <div className={`metric__delta metric__delta--${deltaTone}`}>{delta}</div> : null}
      {spark ? <Sparkline points={spark} color={sparkColor} id={String(label)} /> : null}
    </div>
  );
}
