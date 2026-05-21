import type { ReactNode } from "react";

type PageHeaderProps = {
  eyebrow?: ReactNode;
  title: ReactNode;
  subtitle?: ReactNode;
  badges?: ReactNode[];
  actions?: ReactNode;
};

export function PageHeader({ eyebrow, title, subtitle, badges = [], actions }: PageHeaderProps) {
  return (
    <header className="page-header">
      <div>
        {eyebrow ? <div className="page-header__eyebrow">{eyebrow}</div> : null}
        <h1 className="page-header__title">
          {title}
          {badges.map((badge, index) => (
            <span key={index}>{badge}</span>
          ))}
        </h1>
        {subtitle ? <div className="page-header__subtitle">{subtitle}</div> : null}
      </div>
      {actions ? <div className="page-header__actions">{actions}</div> : null}
    </header>
  );
}
