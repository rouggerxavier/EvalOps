import type { ReactNode } from "react";

import { cn, labelize } from "./utils";

export type BadgeVariant = "default" | "ok" | "warn" | "err" | "info" | "eval" | "rag";

type BadgeProps = {
  variant?: BadgeVariant;
  dot?: boolean;
  children: ReactNode;
  className?: string;
};

export function Badge({ variant = "default", dot = true, children, className }: BadgeProps) {
  return (
    <span className={cn("badge", variant !== "default" && `badge--${variant}`, className)}>
      {dot ? <span className="badge__dot" aria-hidden="true" /> : null}
      {children}
    </span>
  );
}

type StatusBadgeProps = {
  status: string | boolean | null | undefined;
  children?: ReactNode;
};

export function StatusBadge({ status, children }: StatusBadgeProps) {
  const normalized = String(status ?? "unknown").toLowerCase();
  const ok = status === true || ["ok", "passed", "active", "completed", "success"].includes(normalized);
  const err = status === false || ["error", "failed", "revoked", "critical"].includes(normalized);
  const warn = ["partial", "pending", "running", "needs_review", "needs review", "queued"].includes(normalized);
  const variant: BadgeVariant = ok ? "ok" : err ? "err" : warn ? "warn" : "default";
  return <Badge variant={variant}>{children ?? labelize(normalized)}</Badge>;
}
