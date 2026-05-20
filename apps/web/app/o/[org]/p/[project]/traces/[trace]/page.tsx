import Link from "next/link";
import { Flag, GitCompare, Play } from "lucide-react";

import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { SpanWaterfall } from "@/components/SpanWaterfall";
import { RAGSummaryHeader } from "@/components/RAGSummaryHeader";
import { AnswerPreviewCard } from "@/components/AnswerPreviewCard";
import { RetrievalSummaryCard } from "@/components/RetrievalSummaryCard";
import { GroundingQualityCard } from "@/components/GroundingQualityCard";
import { CitationRefsTable } from "@/components/CitationRefsTable";
import { getTrace, hasAuthToken } from "@/lib/api";
import { createTraceFeedbackAction } from "@/lib/actions";
import { formatCost, formatDateTime, formatLatency } from "@/lib/format";
import {
  getAnswerPreview,
  getCitationRefs,
  getGroundingQuality,
  getRagSummary,
  getRetrievalSummary,
  isRagTrace,
} from "@/lib/rag";
import { safeErrorMessage } from "@/lib/safe-error";
import { formatTraceScore, getTraceCauseLabel, getTraceModelLabel } from "@/lib/trace-display";

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

function DetailMetric({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="evo-metric evo-trace-detail__metric">
      <div className="evo-metric__label">{label}</div>
      <div className="evo-metric__value evo-metric__value--mono">{value}</div>
      {hint ? <div className="evo-metric__delta evo-metric__delta--neutral">{hint}</div> : null}
    </div>
  );
}

export default async function TraceDetailPage({ params, searchParams }: Props) {
  const { org, project, trace } = await params;
  const qp = await searchParams;

  if (!(await hasAuthToken())) return <AuthRequiredPanel layout="main" />;

  const detail = await getTrace(trace);
  const t = detail.trace;
  const safeQueryError = qp.error ? safeErrorMessage(qp.error, "Falha ao registrar feedback.") : null;

  const ragEnabled = isRagTrace(detail);
  const ragSummary = ragEnabled ? getRagSummary(detail) : undefined;
  const answerPreview = ragEnabled ? getAnswerPreview(detail) : undefined;
  const retrievalSummary = ragEnabled ? getRetrievalSummary(detail) : undefined;
  const groundingQuality = ragEnabled ? getGroundingQuality(detail) : undefined;
  const citationRefs = ragEnabled ? getCitationRefs(detail) : undefined;
  const traceCause = getTraceCauseLabel(t);
  const traceModel = getTraceModelLabel(t) ?? ragSummary?.model;
  const attentionTitle = t.status === "error" ? "Trace com erro" : t.status === "partial" ? "Trace parcial" : null;
  const ragScore = groundingQuality?.quality_score ?? ragSummary?.quality_score;

  return (
    <main className="evo-page evo-trace-detail">
      <div className="evo-page-header">
        <div>
          <p className="evo-page-header__eyebrow">Observabilidade · Trace detail</p>
          <div className="evo-trace-detail__title-row">
            <h1 className="evo-page-header__title" style={{ margin: 0 }}>{t.name}</h1>
            <StatusBadge status={t.status} />
            <span className="evo-tag">{t.environment}</span>
            {ragEnabled ? <span className="evo-badge evo-badge--eval">RAG</span> : null}
            {t.redacted ? <span className="evo-tag">Redigido</span> : null}
          </div>
          <div className="evo-trace-detail__meta">
            <span className="evo-mono" style={{ fontSize: 11 }}>{t.id}</span>
            {t.service && <span>{t.service}</span>}
            {traceModel && <span className="evo-mono">{traceModel}</span>}
            <span>{formatDateTime(t.created_at)}</span>
            {t.user_ref && <span className="evo-mono">user: {t.user_ref}</span>}
          </div>
        </div>
        <div className="evo-page-header__actions">
          <button
            type="button"
            className="evo-btn evo-btn--sm"
            disabled
            data-status="planned"
            title="Flag manual — em breve"
          >
            <Flag size={13} /> Flagear
          </button>
          <button
            type="button"
            className="evo-btn evo-btn--sm"
            disabled
            data-status="planned"
            title="Reexecução de trace — em breve"
          >
            <Play size={13} /> Reexecutar
          </button>
          <button
            type="button"
            className="evo-btn evo-btn--sm"
            disabled
            data-status="planned"
            title="Comparação de traces — em breve"
          >
            <GitCompare size={13} /> Comparar
          </button>
          <Link className="evo-btn evo-btn--sm" href={`/o/${org}/p/${project}/traces`}>
            ← Traces
          </Link>
        </div>
      </div>

      {attentionTitle && (
        <div className={`evo-trace-attention evo-trace-attention--${t.status === "error" ? "error" : "partial"}`}>
          <div>
            <strong>{attentionTitle}</strong>
            <span>
              {traceCause
                ? `Causa informada: ${traceCause}.`
                : "Sem causa estruturada em metadata; confira waterfall e JSON cru."}
            </span>
          </div>
          <span className="evo-tag">{t.status}</span>
        </div>
      )}

      <div className="evo-kpi-grid evo-trace-detail__kpis">
        <DetailMetric label="Duração" value={formatLatency(t.duration_ms)} hint="tempo total" />
        <DetailMetric label="Tokens entrada" value={t.total_tokens_in.toLocaleString("pt-BR")} />
        <DetailMetric label="Tokens saída" value={t.total_tokens_out.toLocaleString("pt-BR")} />
        <DetailMetric label="Custo" value={formatCost(t.total_cost_usd)} />
        <DetailMetric label="Spans / Eventos" value={`${detail.spans.length} / ${detail.events_count}`} />
        <DetailMetric
          label="Qualidade RAG"
          value={ragScore === undefined ? "—" : formatTraceScore(ragScore)}
          hint={ragEnabled ? "sinal capturado" : "não-RAG"}
        />
      </div>

      {ragEnabled && (
        <section
          aria-label="RAG details"
          className="evo-trace-section evo-trace-section--rag"
          data-testid="rag-section"
        >
          <div className="evo-trace-section__header">
            <div>
              <h2>RAG</h2>
              <p>Resposta, retrieval, grounding e citações preservados do emissor do trace.</p>
            </div>
          </div>
          {ragSummary && <RAGSummaryHeader summary={ragSummary} />}
          <div className="evo-rag-grid">
            {answerPreview && <AnswerPreviewCard answer={answerPreview} />}
            {groundingQuality && <GroundingQualityCard quality={groundingQuality} />}
            {retrievalSummary && <RetrievalSummaryCard retrieval={retrievalSummary} />}
            {citationRefs && <CitationRefsTable citations={citationRefs} />}
          </div>
        </section>
      )}

      <section className="evo-trace-section" data-testid="trace-waterfall-section">
        <div className="evo-trace-section__header">
          <div>
            <h2>Waterfall</h2>
            <p>Ordem dos spans, duração relativa e payload do span selecionado.</p>
          </div>
        </div>
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
      </section>

      <div className="evo-trace-detail__bottom">
        <div className="evo-card">
          <div className="evo-card__header">
            <div>
              <h3 className="evo-card__title">Metadata do trace</h3>
              <p className="evo-card__subtitle">JSON cru preservado para inspeção.</p>
            </div>
          </div>
          <div className="evo-card__body">
            <div className="evo-code">
              <pre className="evo-code__body" style={{ margin: 0, maxHeight: 240, overflowY: "auto" }}>
                {JSON.stringify(t.metadata, null, 2)}
              </pre>
            </div>
          </div>
        </div>

        <div className="evo-trace-feedback-rail">
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
              {safeQueryError && (
                <div style={{ marginBottom: 12, padding: "8px 12px", background: "var(--err-bg)", border: "1px solid var(--err-border)", borderRadius: 6, fontSize: 13, color: "var(--err)" }}>
                  {safeQueryError}
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
