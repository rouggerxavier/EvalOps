import type { ReactNode } from "react";
import { AlertTriangle } from "lucide-react";

type AttentionStripProps = {
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
};

export function AttentionStrip({ title, description, action }: AttentionStripProps) {
  return (
    <div className="attention">
      <div className="attention__icon">
        <AlertTriangle size={16} aria-hidden="true" />
      </div>
      <div>
        <div className="attention__title">{title}</div>
        {description ? <div className="attention__desc">{description}</div> : null}
      </div>
      {action}
    </div>
  );
}
