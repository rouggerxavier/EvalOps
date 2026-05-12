import Link from "next/link";
import { Flag, GitCompare, Play } from "lucide-react";

import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { SpanWaterfall } from "@/components/SpanWaterfall";
import { getTrace, hasAuthToken } from "@/lib/api";
import { createTraceFeedbackAction } from "@/lib/actions";
import { formatCost, formatDateTime, formatLatency } from "@/lib/format";

type Props = {
  params: Promise<{ org: string; project: string; trace: string }>;
  searchParams: Promise<{ feedback?: string; error?: string }>;
};

function StatusBadge({ status }: { status: string }) {
  const cls = status === "ok" ? "evo-badge--ok" : status === "error" ? "evo-badge--err" : "evo-badge--warn";
  return (
    <span className={`evo-badge ${cls}`}>
      <span className="evo-badge__dot" />
      {status.toUpperCase()}
    </span>
  );
}

export default async function TraceDetailPage({ params, searchParams }: Props) {
  const { org, project, trace } = await params;
  const qp = await searchParams;

  if (!(await hasAuthToken())) return <AuthRequiredPanel layout="main" />;

  const detail = await getTrace(trace);
  const t = detail.trace;

  return (
    <main className="evo-page">
      {/* ── Header ── */}
      <div className="evo-page-header">
        <div>
          <div className="evo-row" style={{ marginBottom: 8 }}>
            <h1 className="evo-page-header__title" style={{ margin: 0 }}>{t.name}</h1>
            <StatusBadge status={t.status} />
            <span className="evo-tag">{t.environment}</span>
          </div>
          <div className="evo-row" style={{ fontSize: 12, color: "var(--text-muted)", gap: 12 }}>
            <span className="evo-mono" style={{ fontSize: 11 }}>{t.id}</span>
            <span>·</span>
            {t.service && <><span>{t.service}</span><span>·</span></>}
            <span>{formatDateTime(t.created_at)}</span>
            {t.user_ref && <><span>·</span><span className="evo-mono">user: {t.user_ref}</span></>}
          </div>
        </div>
        <div className="evo-row">
          <button type="button" className="evo-btn evo-btn--sm"><Flag size={13} /> Flagear</button>
          <button type="button" className="evo-btn evo-btn--sm"><Play size={13} /> Reexecutar</button>
          <button type="button" className="evo-btn evo-btn--sm"><GitCompare size={13} /> Comparar</button>
          <Link className="evo-btn evo-btn--sm" href={`/o/${org}/p/${project}/traces`}>
            ← Traces
          </Link>
        </div>
      </div>

      {/* ── KPI grid ── */}
      <div className="evo-kpi-grid" style={{ gridTemplateColumns: "repeat(5, minmax(0,1fr))" }}>
        <div className="evo-metric">
          <div className="evo-metric__label">Duração</div>
          <div className="evo-metric__value evo-metric__value--mono">
            {(t.duration_ms / 1000).toFixed(2)}<span className="evo-metric__unit">s</span>
          </div>
        </div>
        <div className="evo-metric">
          <div className="evo-metric__label">Tokens entrada</div>
          <div className="evo-metric__value evo-metric__value--mono">
            {t.total_tokens_in.toLocaleString("pt-BR")}
          </div>
        </div>
        <div className="evo-metric">
          <div className="evo-metric__label">Tokens saída</div>
          <div className="evo-metric__value evo-metric__value--mono">
            {t.total_tokens_out.toLocaleString("pt-BR")}
          </div>
        </div>
        <div className="evo-metric">
          <div className="evo-metric__label">Custo</div>
          <div className="evo-metric__value evo-metric__value--mono">
            {formatCost(t.total_cost_usd)}
          </div>
        </div>
        <div className="evo-metric">
          <div className="evo-metric__label">Spans / Eventos</div>
          <div className="evo-metric__value evo-metric__value--mono">
            {detail.spans.length}<span className="evo-metric__unit">/ {detail.events_count}</span>
          </div>
        </div>
      </div>

      {/* ── Waterfall ── */}
      <div style={{ marginBottom: "var(--sp-3)" }}>
        <h2 style={{ fontSize: "var(--fs-14)", fontWeight: 600, color: "var(--text)", marginBottom: "var(--sp-3)" }}>
          Waterfall
        </h2>
        {detail.spans.length === 0 ? (
          <div className="evo-card" style={{ padding: "40px 24px", textAlign: "center" }}>
            <p style={{ color: "var(--text-muted)" }}>Nenhum span capturado neste trace.</p>
          </div>
        ) : (
          <SpanWaterfall
            spans={detail.spans}
            traceDurationMs={t.duration_ms}
            traceStartedAt={t.started_at}
          />
        )}
      </div>

      {/* ── Bottom grid: metadata + feedback ── */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 340px", gap: "var(--sp-3)" }}>
        {/* Metadata */}
        <div className="evo-card">
          <div className="evo-card__header">
            <h3 className="evo-card__title">Metadata do trace</h3>
          </div>
          <div className="evo-card__body">
            <div className="evo-code">
              <pre className="evo-code__body" style={{ margin: 0, maxHeight: 240, overflowY: "auto" }}>
                {JSON.stringify(t.metadata, null, 2)}
              </pre>
            </div>
          </div>
        </div>

        {/* Feedback rail */}
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-3)" }}>
          <div className="evo-card">
            <div className="evo-card__header">
              <h3 className="evo-card__title">Feedback humano</h3>
            </div>
            <div className="evo-card__body">
              {qp.feedback === "1" && (
                <div style={{ marginBottom: 12, padding: "8px 12px", background: "var(--ok-bg)", border: "1px solid var(--ok-border)", borderRadius: 6, fontSize: 13, color: "var(--ok)" }}>
                  Feedback registrado com sucesso.
                </div>
              )}
              {qp.error && (
                <div style={{ marginBottom: 12, padding: "8px 12px", background: "var(--err-bg)", border: "1px solid var(--err-border)", borderRadius: 6, fontSize: 13, color: "var(--err)" }}>
                  {qp.error}
                </div>
              )}
              <form action={createTraceFeedbackAction} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                <input type="hidden" name="org" value={org} />
                <input type="hidden" name="project" value={project} />
                <input type="hidden" name="trace_id" value={t.id} />
                <div>
                  <label style={{ display: "block", fontSize: 12, color: "var(--text-muted)", marginBottom: 4 }}>Avaliação</label>
                  <select name="thumbs" defaultValue="up" style={{
                    width: "100%", height: 32, background: "var(--surface-2)", border: "1px solid var(--border-default)",
                    borderRadius: 6, color: "var(--text)", fontSize: 13, padding: "0 8px",
                  }}>
                    <option value="up">👍 Positivo</option>
                    <option value="down">👎 Negativo</option>
                  </select>
                </div>
                <div>
                  <label style={{ display: "block", fontSize: 12, color: "var(--text-muted)", marginBottom: 4 }}>Comentário</label>
                  <input name="comment" placeholder="O que aconteceu neste trace?" style={{
                    width: "100%", height: 32, background: "var(--surface-2)", border: "1px solid var(--border-default)",
                    borderRadius: 6, color: "var(--text)", fontSize: 13, padding: "0 10px",
                  }} />
                </div>
                <button type="submit" className="evo-btn evo-btn--primary" style={{ justifyContent: "center" }}>
                  Enviar feedback
                </button>
              </form>
            </div>
          </div>

          {detail.feedback.length > 0 && (
            <div className="evo-card">
              <div className="evo-card__header">
                <h3 className="evo-card__title">Histórico</h3>
                <span className="evo-tab__count">{detail.feedback.length}</span>
              </div>
              <div className="evo-card__body" style={{ padding: 0 }}>
                {detail.feedback.map((fb) => (
                  <div key={fb.id} style={{
                    padding: "10px 16px",
                    borderBottom: "1px solid var(--border-subtle)",
                    display: "flex",
                    flexDirection: "column",
                    gap: 4,
                  }}>
                    <div className="evo-row" style={{ justifyContent: "space-between" }}>
                      <span style={{ fontSize: 13 }}>{fb.thumbs === "up" ? "👍" : "👎"} {fb.thumbs}</span>
                      <span style={{ fontSize: 11, color: "var(--text-faint)" }}>{formatDateTime(fb.created_at)}</span>
                    </div>
                    {fb.comment && <p style={{ margin: 0, fontSize: 12, color: "var(--text-muted)" }}>{fb.comment}</p>}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
