import type { ReactNode } from "react";

type FlashProps = {
  kind: "success" | "error";
  message: string;
};

export function Flash({ kind, message }: FlashProps) {
  return <div className={`flash flash--${kind}`}>{message}</div>;
}

type SectionHeadProps = {
  title: string;
  description?: string;
  action?: ReactNode;
};

export function SectionHead({ title, description, action }: SectionHeadProps) {
  return (
    <div className="section-head">
      <div>
        <h2>{title}</h2>
        {description ? <p>{description}</p> : null}
      </div>
      {action ? <div className="actions-row">{action}</div> : null}
    </div>
  );
}

type StatusBadgeProps = {
  status: string | boolean | null | undefined;
  children?: ReactNode;
};

export function StatusBadge({ status, children }: StatusBadgeProps) {
  const normalized = String(status ?? "unknown").toLowerCase();
  const isAprovado = status === true || ["ok", "passed", "active", "completed", "success"].includes(normalized);
  const isFalhou = status === false || ["error", "failed", "revoked", "critical"].includes(normalized);
  const isReview = ["partial", "pending", "running", "needs_review", "needs review", "queued"].includes(normalized);
  const className = isAprovado
    ? "badge badge--passed"
    : isFalhou
      ? "badge badge--failed"
      : isReview
        ? "badge badge--review"
        : "badge badge--neutral";
  const label = children ?? (
    isAprovado ? "Aprovado" : isFalhou ? "Falhou" : isReview ? labelize(normalized) : labelize(normalized)
  );
  return <span className={className}>{label}</span>;
}

export function EnvBadge({ children }: { children: ReactNode }) {
  return <span className="badge badge--env">{children}</span>;
}

export function ScoreCell({ value }: { value: number | null | undefined }) {
  if (value === null || value === undefined) return <span className="table-meta">Sem score</span>;
  const cls = value >= 0.7 ? "" : value >= 0.4 ? " warn" : " bad";
  return (
    <span className="score-cell">
      <span className="v">{value.toFixed(2)}</span>
      <span className={`score-bar${cls}`}>
        <i style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }} />
      </span>
    </span>
  );
}

export function JsonBlock({ value }: { value: unknown }) {
  const text = typeof value === "string" ? value : JSON.stringify(value ?? "-", null, 2);
  return (
    <pre className="code-block">
      <code>{text}</code>
    </pre>
  );
}

export function EmptyState({
  title,
  description,
  steps,
  snippet,
}: {
  title: string;
  description: string;
  steps?: string[];
  snippet?: string;
}) {
  return (
    <div className="quickstart">
      <h3>{title}</h3>
      <p>{description}</p>
      {steps?.length ? (
        <ol>
          {steps.map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>
      ) : null}
      {snippet ? (
        <pre>
          <code>{snippet}</code>
        </pre>
      ) : null}
    </div>
  );
}

function labelize(value: string): string {
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}


