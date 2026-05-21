import type { ReactNode } from "react";

type EmptyStateProps = {
  icon?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  code?: string;
  action?: ReactNode;
};

export function EmptyState({ icon, title, description, code, action }: EmptyStateProps) {
  return (
    <div className="empty">
      {icon ? <div className="empty__icon">{icon}</div> : null}
      <div className="empty__title">{title}</div>
      {description ? <div className="empty__desc">{description}</div> : null}
      {action}
      {code ? <pre className="empty__code">{code}</pre> : null}
    </div>
  );
}
