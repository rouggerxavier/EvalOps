import type { ReactNode } from "react";

import { cn } from "./utils";

type CardProps = {
  title?: ReactNode;
  subtitle?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  flush?: boolean;
  className?: string;
};

export function Card({ title, subtitle, action, children, flush = false, className }: CardProps) {
  const hasHeader = title || subtitle || action;

  return (
    <section className={cn("card", className)}>
      {hasHeader ? (
        <div className="card__header">
          <div>
            {title ? <h3 className="card__title">{title}</h3> : null}
            {subtitle ? <div className="card__subtitle">{subtitle}</div> : null}
          </div>
          {action ? <div className="row">{action}</div> : null}
        </div>
      ) : null}
      <div className={cn("card__body", flush && "card__body--flush")}>{children}</div>
    </section>
  );
}
