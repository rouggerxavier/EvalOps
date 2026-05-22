import Link from "next/link";
import { Activity, AlertCircle, Copy, Flag as FlagIcon, Layers, Terminal } from "lucide-react";

import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { Copyable } from "@/components/ui/Copyable";
import { JsonBlock } from "@/components/ui/JsonBlock";
import { Metric } from "@/components/ui/Metric";
import { RagPanel } from "@/components/ui/RagPanel";
import { ScoreCell } from "@/components/ui/ScoreCell";
import { Waterfall } from "@/components/ui/Waterfall";
import { createTraceFeedbackAction } from "@/lib/actions";
import {
  getRubrics,
  getTrace,
  getTraceRag,
  getTraces,
  hasAuthToken,
} from "@/lib/api";
import { formatCost, formatLatency, formatRelativeTime } from "@/lib/format";
import { isRagTrace } from "@/lib/rag";
import { safeErrorMessage } from "@/lib/safe-error";
import { getTraceCauseLabel, getTraceModelLabel } from "@/lib/trace-display";
import type { RagConsolidated } from "@/lib/types";

import { TraceHeaderActions } from "./trace-actions";

type Tab = "rag" | "waterfall" | "metadata" | "feedback";

type Props = {
  params: Promise<{ org: string; project: string; trace: string }>;
  searchParams: Promise<{
    tab?: string;
    feedback?: string;
    flagged?: string;
    rerun?: string;
    new_trace_id?: string;
    error?: string;
  }>;
};

function costSourceLabel(source: string | null | undefined): string | undefined {
  // Translates the backend `cost_source` enum into copy honest about how the
  // total was derived. Returns undefined for `priced` so the metric falls back
  // to the model name (default neutral state).
  if (source === "provided") return "valor enviado pelo cliente";
  if (source === "estimated") return "sem preço — estimado por tokens";
  if (source === "unknown") return "sem preço nem tokens";
  return undefined;
}

function parseTab(value: string | undefined, hasRag: boolean): Tab {
  if (value === "rag" && hasRag) return "rag";
  if (value === "waterfall" || value === "metadata" || value === "feedback") return value;
  return hasRag ? "rag" : "waterfall";
}

export default async function TraceDetailPage({ params, searchParams }: Props) {
  const { org, project, trace } = await params;
  const qp = await searchParams;

  if (!(await hasAuthToken())) return <AuthRequiredPanel layout="main" />;

  const detail = await getTrace(trace);
  const t = detail.trace;
  const ragEnabled = isRagTrace(detail);

  const tab = parseTab(qp.tab, ragEnabled);
  const safeQueryError = qp.error ? safeErrorMessage(qp.error, "Falha em ação.") : null;

  const [rubricsRes, compareList, ragData] = await Promise.all([
    getRubrics(t.project_id).catch(() => ({ data: [] })),
    getTraces({ projectId: t.project_id, limit: 12 }).catch(() => ({ data: [], next_cursor: null })),
    ragEnabled ? getTraceRag(t.id).catch(() => null as RagConsolidated | null) : Promise.resolve(null),
  ]);

  const compareCandidates = compareList.data.filter((row) => row.id !== t.id).slice(0, 10);
  const traceCause = getTraceCauseLabel(t);
  const traceModel = getTraceModelLabel(t);

  const replayOf = typeof t.metadata?.replay_of === "string" ? (t.metadata.replay_of as string) : null;
  const replayStatusRaw = typeof t.metadata?.replay_status === "string" ? (t.metadata.replay_status as string) : null;
  const replayStatus: "queued" | "running" | "completed" | "failed" | null =
    replayStatusRaw === "queued" || replayStatusRaw === "running" || replayStatusRaw === "completed" || replayStatusRaw === "failed"
      ? replayStatusRaw
      : null;
  const replayError = typeof t.metadata?.replay_error === "string" ? (t.metadata.replay_error as string) : null;
  const replayBadgeVariant: "info" | "warn" | "ok" | "err" =
    replayStatus === "completed"
      ? "ok"
      : replayStatus === "failed"
      ? "err"
      : replayStatus === "running"
      ? "warn"
      : "info";

  const tabBase = `/o/${org}/p/${project}/traces/${t.id}`;
  const tabHref = (next: Tab) => `${tabBase}?tab=${next}`;

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <div className="page-header__eyebrow">
            <Link href={`/o/${org}/p/${project}/traces`} style={{ color: "var(--primary-400)" }}>
              ← Traces
            </Link>
          </div>
          <h1 className="page-header__title" style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span className="mono" style={{ fontSize: 17, fontWeight: 500 }}>{t.name}</span>
            <StatusBadge status={t.status} />
            <span className="tag">{t.environment}</span>
            {ragEnabled ? <Badge variant="rag">RAG</Badge> : null}
            {t.redacted ? <span className="tag">redigido</span> : null}
            {replayStatus ? (
              <Badge variant={replayBadgeVariant}>replay · {replayStatus}</Badge>
            ) : null}
          </h1>
          <div
            className="page-header__subtitle row"
            style={{ gap: 10, fontFamily: "var(--font-mono)", fontSize: 11.5 }}
          >
            <Copyable value={t.id} display={`${t.id.slice(0, 18)}…`} />
            {t.service ? <><span>·</span><span>{t.service}</span></> : null}
            {traceModel ? <><span>·</span><span>{traceModel}</span></> : null}
            <span>·</span>
            <span>{formatRelativeTime(t.created_at)}</span>
            {t.user_ref ? <><span>·</span><span>user: {t.user_ref}</span></> : null}
          </div>
        </div>
        <div className="page-header__actions">
          <TraceHeaderActions
            org={org}
            project={project}
            traceId={t.id}
            rubrics={rubricsRes.data}
            compareCandidates={compareCandidates}
          />
        </div>
      </header>

      {qp.flagged === "1" ? (
        <div className="attention" style={{ borderColor: "rgba(154,122,255,0.4)" }}>
          <div className="attention__icon"><FlagIcon size={14} /></div>
          <div>
            <div className="attention__title">Trace flagged</div>
            <div className="attention__desc">Registro criado em trace_flags.</div>
          </div>
        </div>
      ) : null}
      {qp.rerun === "1" && qp.new_trace_id ? (
        <div className="attention" style={{ borderColor: "rgba(90,212,212,0.4)" }}>
          <div className="attention__icon"><Activity size={14} /></div>
          <div>
            <div className="attention__title">Reexecução enfileirada</div>
            <div className="attention__desc">
              Novo trace:{" "}
              <Link href={`/o/${org}/p/${project}/traces/${qp.new_trace_id}`} className="mono">
                {qp.new_trace_id}
              </Link>
              . Worker processa em background — recarregue para ver o status.
            </div>
          </div>
        </div>
      ) : null}
      {replayOf ? (
        <div
          className="attention"
          style={{
            borderColor:
              replayStatus === "failed"
                ? "rgba(255,99,99,0.4)"
                : replayStatus === "completed"
                ? "rgba(120,200,120,0.4)"
                : "rgba(90,212,212,0.4)",
          }}
        >
          <div className="attention__icon">
            {replayStatus === "failed" ? <AlertCircle size={14} /> : <Activity size={14} />}
          </div>
          <div>
            <div className="attention__title">
              Replay de{" "}
              <Link href={`/o/${org}/p/${project}/traces/${replayOf}`} className="mono">
                {replayOf}
              </Link>
              {replayStatus ? <> · status: <span className="mono">{replayStatus}</span></> : null}
            </div>
            <div className="attention__desc">
              {replayStatus === "queued" || replayStatus === "running"
                ? "Worker em execução. Recarregue para atualizar."
                : replayStatus === "failed"
                ? `Falha no worker${replayError ? `: ${replayError}` : "."}`
                : replayStatus === "completed"
                ? "Replay concluído — métricas refletem a nova execução."
                : "Status do replay não disponível."}
            </div>
          </div>
        </div>
      ) : null}
      {safeQueryError ? (
        <div className="attention" style={{ borderColor: "rgba(255,99,99,0.4)" }}>
          <div className="attention__icon"><AlertCircle size={14} /></div>
          <div>
            <div className="attention__title">Falha</div>
            <div className="attention__desc">{safeQueryError}</div>
          </div>
        </div>
      ) : null}

      {t.status === "error" ? (
        <div
          className="attention"
          style={{ marginBottom: 16, borderColor: "rgba(255,99,99,0.4)" }}
        >
          <div className="attention__icon"><AlertCircle size={14} /></div>
          <div>
            <div className="attention__title">Trace com erro</div>
            <div className="attention__desc">
              {traceCause ? <>Causa: <span className="mono">{traceCause}</span></> : "Sem causa estruturada em metadata."}
            </div>
          </div>
        </div>
      ) : null}

      <section className="kpi-grid kpi-grid--5">
        <Metric label="Duração" value={formatLatency(t.duration_ms)} delta="tempo total" deltaTone="neutral" />
        <Metric
          label="Tokens entrada"
          value={t.total_tokens_in.toLocaleString("pt-BR")}
          delta="prompt"
          deltaTone="neutral"
        />
        <Metric
          label="Tokens saída"
          value={t.total_tokens_out.toLocaleString("pt-BR")}
          delta="completion"
          deltaTone="neutral"
        />
        <Metric
          label="Custo"
          value={formatCost(t.total_cost_usd)}
          delta={costSourceLabel(t.cost_source) ?? (traceModel ?? "sem modelo")}
          deltaTone={t.cost_source && t.cost_source !== "priced" ? "down" : "neutral"}
        />
        <Metric
          label="Spans / Eventos"
          value={`${detail.spans.length}`}
          unit={`/ ${detail.events_count}`}
          delta="capturados"
          deltaTone="neutral"
        />
      </section>

      <nav className="tabs">
        {ragEnabled ? (
          <Link href={tabHref("rag")} className={`tab${tab === "rag" ? " is-active" : ""}`}>
            <Layers size={11} /> RAG
          </Link>
        ) : null}
        <Link href={tabHref("waterfall")} className={`tab${tab === "waterfall" ? " is-active" : ""}`}>
          <Activity size={11} /> Waterfall
          <span className="tab__count">{detail.spans.length}</span>
        </Link>
        <Link href={tabHref("metadata")} className={`tab${tab === "metadata" ? " is-active" : ""}`}>
          <Terminal size={11} /> Metadata
        </Link>
        <Link href={tabHref("feedback")} className={`tab${tab === "feedback" ? " is-active" : ""}`}>
          <FlagIcon size={11} /> Feedback
          <span className="tab__count">{detail.feedback.length}</span>
        </Link>
      </nav>

      {tab === "rag" && ragEnabled ? (
        ragData ? (
          <div className="col">
            <div className="rag-header">
              <div className="rag-header__title">
                <Badge variant="rag">RAG</Badge>
                <strong>Grounding</strong>
              </div>
              <div>
                <div className="rag-stat__label">Docs recuperados</div>
                <div className="rag-stat__value">{ragData.retrieved_docs}</div>
              </div>
              <div>
                <div className="rag-stat__label">Score médio</div>
                <div className="rag-stat__value">
                  {ragData.avg_score === null ? "—" : ragData.avg_score.toFixed(2)}
                </div>
              </div>
              <div>
                <div className="rag-stat__label">Claims grounded</div>
                <div className="rag-stat__value">
                  <span style={{ color: "var(--success)" }}>{ragData.grounded_claims}</span>
                  <span className="faint"> / {ragData.grounded_claims + ragData.ungrounded_claims}</span>
                </div>
              </div>
              <div>
                <div className="rag-stat__label">Risco</div>
                <div
                  className="rag-stat__value"
                  style={{
                    color:
                      ragData.hallucination_risk === "low"
                        ? "var(--success)"
                        : ragData.hallucination_risk === "medium"
                        ? "var(--warning)"
                        : "var(--danger)",
                    textTransform: "capitalize",
                  }}
                >
                  {ragData.hallucination_risk}
                </div>
              </div>
            </div>
            <RagPanel
              retrievedDocs={ragData.retrieved_docs}
              avgScore={ragData.avg_score ?? undefined}
              groundedClaims={ragData.grounded_claims}
              hallucinationRisk={ragData.hallucination_risk}
              answerPreview={ragData.answer_preview ?? undefined}
              citations={ragData.citations.map((c) => ({
                rank: c.rank,
                title: c.title ?? "—",
                score: c.score ?? undefined,
                source: c.source ?? undefined,
                chunk: c.chunk ?? undefined,
              }))}
              claims={ragData.claims.map((cl) => ({
                text: cl.text,
                grounded: cl.grounded,
                cite: cl.cite ?? undefined,
              }))}
            />
            {ragData.claim_to_chunk.length > 0 ? (
              <Card title="Citação por claim" subtitle="qual claim usou qual chunk" flush>
                <table className="t">
                  <thead>
                    <tr><th>Claim</th><th>Chunk</th><th>Score</th></tr>
                  </thead>
                  <tbody>
                    {ragData.claim_to_chunk.map((row, i) => (
                      <tr key={i}>
                        <td className="t__name">{row.claim}</td>
                        <td className="t__mono">{row.chunk}</td>
                        <td>
                          {row.score === null ? (
                            <span className="faint mono">ungrounded</span>
                          ) : (
                            <ScoreCell value={row.score} />
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Card>
            ) : null}
          </div>
        ) : (
          <Card title="RAG" subtitle="sem dados consolidados">
            <p className="muted" style={{ margin: 0 }}>
              Endpoint <span className="mono">/v1/traces/{`{id}`}/rag</span> não retornou dados.
            </p>
          </Card>
        )
      ) : null}

      {tab === "waterfall" ? (
        <Card title="Waterfall" subtitle={`${detail.spans.length} spans · escala absoluta`} flush>
          {detail.spans.length === 0 ? (
            <div className="t__empty">Nenhum span capturado neste trace.</div>
          ) : (
            <Waterfall
              spans={detail.spans}
              traceDurationMs={t.duration_ms}
              traceStartedAt={t.started_at}
            />
          )}
        </Card>
      ) : null}

      {tab === "metadata" ? (
        <div className="grid-detail">
          <Card
            title="Metadata do trace"
            subtitle="JSON raw · armazenado em traces.metadata"
            action={
              <a
                className="btn btn--sm btn--ghost"
                href={`data:application/json;charset=utf-8,${encodeURIComponent(JSON.stringify(t.metadata, null, 2))}`}
                download={`${t.id}.metadata.json`}
              >
                <Copy size={12} /> Baixar JSON
              </a>
            }
          >
            <JsonBlock value={t.metadata} />
          </Card>
        </div>
      ) : null}

      {tab === "feedback" ? (
        <div className="grid-detail">
          <Card
            title="Histórico de feedback"
            subtitle={`${detail.feedback.length} entrada${detail.feedback.length === 1 ? "" : "s"}`}
            flush
          >
            {detail.feedback.length === 0 ? (
              <div className="t__empty">Nenhum feedback humano registrado ainda.</div>
            ) : (
              detail.feedback.map((fb) => (
                <div
                  key={fb.id}
                  style={{
                    padding: "10px 16px",
                    borderBottom: "1px solid var(--border-subtle)",
                    display: "flex",
                    flexDirection: "column",
                    gap: 4,
                  }}
                >
                  <div className="row" style={{ justifyContent: "space-between" }}>
                    <span style={{ fontSize: 13 }}>
                      {fb.thumbs === "up" ? "👍" : fb.thumbs === "down" ? "👎" : "•"}{" "}
                      <span className="mono faint" style={{ fontSize: 11 }}>{fb.source}</span>
                    </span>
                    <span className="faint mono" style={{ fontSize: 10 }}>
                      {formatRelativeTime(fb.created_at)}
                    </span>
                  </div>
                  {fb.comment ? (
                    <p style={{ margin: 0, fontSize: 12, color: "var(--fg-2)" }}>{fb.comment}</p>
                  ) : null}
                </div>
              ))
            )}
          </Card>
          <Card title="Registrar feedback" subtitle="POST /v1/traces/{id}/feedback">
            {qp.feedback === "1" ? (
              <div
                style={{
                  marginBottom: 12,
                  padding: "8px 12px",
                  border: "1px solid var(--success)",
                  borderRadius: "var(--r-sm)",
                  fontSize: 13,
                  color: "var(--success)",
                }}
              >
                Feedback registrado com sucesso.
              </div>
            ) : null}
            <form
              action={createTraceFeedbackAction}
              style={{ display: "flex", flexDirection: "column", gap: 10 }}
            >
              <input type="hidden" name="org" value={org} />
              <input type="hidden" name="project" value={project} />
              <input type="hidden" name="trace_id" value={t.id} />
              <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <span style={{ fontSize: 11, color: "var(--fg-3)" }}>Avaliação</span>
                <select className="filter-select" name="thumbs" defaultValue="up">
                  <option value="up">👍 Positivo</option>
                  <option value="down">👎 Negativo</option>
                </select>
              </label>
              <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <span style={{ fontSize: 11, color: "var(--fg-3)" }}>Comentário</span>
                <input
                  className="filter-input"
                  name="comment"
                  placeholder="O que aconteceu neste trace?"
                  style={{ height: 32, padding: "0 10px" }}
                />
              </label>
              <button type="submit" className="btn btn--sm btn--primary" style={{ justifyContent: "center" }}>
                Enviar feedback
              </button>
            </form>
          </Card>
        </div>
      ) : null}
    </div>
  );
}

