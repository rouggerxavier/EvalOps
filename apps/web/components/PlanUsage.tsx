import { formatCost, formatCount } from "@/lib/format";
import type { OrgSubscription, OrgUsage } from "@/lib/types";

function percent(value: number, limit: number): number {
  if (!limit || limit <= 0) return 0;
  return Math.max(0, Math.min(100, (value / limit) * 100));
}

function UsageBar({ label, value, limit }: { label: string; value: number; limit: number }) {
  const pct = percent(value, limit);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "var(--text-muted)" }}>
        <span>{label}</span>
        <span className="mono">{formatCount(value)} / {formatCount(limit)}</span>
      </div>
      <div style={{ height: 6, background: "var(--bg-2)", borderRadius: 999, overflow: "hidden" }}>
        <div style={{ width: `${pct}%`, height: "100%", background: pct > 90 ? "var(--warn)" : "var(--accent)" }} />
      </div>
    </div>
  );
}

type Props = {
  usage: OrgUsage | null;
  usageError: string | null;
  subscription: OrgSubscription | null;
  subscriptionError: string | null;
};

export function PlanUsage({ usage, usageError, subscription, subscriptionError }: Props) {
  return (
    <section className="card">
      <div className="card__header">
        <h3 className="card__title">Plano e uso</h3>
      </div>
      <div className="card__body" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {subscription ? (
          <>
            <div>
              <div style={{ color: "var(--text)", fontSize: 14, fontWeight: 600 }}>{subscription.plan.name}</div>
              <div style={{ color: "var(--text-faint)", fontSize: 12 }}>{subscription.plan.code}</div>
            </div>
            {usage ? (
              <>
                <div className="mono" style={{ color: "var(--text)", fontSize: 18 }}>
                  {formatCost(usage.cost_usd)}
                </div>
                <div style={{ color: "var(--text-faint)", fontSize: 12 }}>período: {usage.period}</div>
                <UsageBar label="Traces" value={usage.traces_ingested} limit={subscription.plan.monthly_trace_limit} />
                <UsageBar label="Avaliações" value={usage.evaluations_run} limit={subscription.plan.monthly_eval_limit} />
                <UsageBar label="Exports" value={usage.exports_created} limit={subscription.plan.monthly_export_limit} />
                <UsageBar label="Spans" value={usage.spans_ingested} limit={subscription.plan.monthly_span_limit} />
                <UsageBar label="Tokens" value={usage.tokens_ingested} limit={subscription.plan.monthly_token_limit} />
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "baseline",
                    borderTop: "1px solid var(--border-subtle)",
                    paddingTop: 10,
                  }}
                >
                  <span style={{ color: "var(--text-muted)", fontSize: 12 }}>Orçamento mensal do juiz</span>
                  <span className="mono" style={{ color: "var(--text)", fontSize: 13 }}>
                    {formatCost(subscription.plan.monthly_judge_budget_usd)}
                  </span>
                </div>
                <p style={{ margin: 0, color: "var(--text-faint)", fontSize: 12 }}>
                  Sem troca de plano pela tela. Para mudar limites, use <span className="mono">scripts/set_org_limits.py</span>.
                </p>
              </>
            ) : (
              <p style={{ margin: 0, color: "var(--warn)", fontSize: 12 }}>Falha ao carregar uso: {usageError}</p>
            )}
          </>
        ) : (
          <p style={{ margin: 0, color: "var(--warn)", fontSize: 12 }}>
            Falha ao carregar assinatura: {subscriptionError}
          </p>
        )}
      </div>
    </section>
  );
}
