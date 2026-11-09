import Link from "next/link";
import { notFound } from "next/navigation";
import { Activity, AlertCircle, Copy, Flag as FlagIcon, Layers, MessageSquare, Target, Terminal } from "lucide-react";

import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { projectHref } from "@/components/app-shell-nav";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { Copyable } from "@/components/ui/Copyable";
import { JsonBlock } from "@/components/ui/JsonBlock";
import { Metric } from "@/components/ui/Metric";
import { RagPanel } from "@/components/ui/RagPanel";
import { createTraceFeedbackAction } from "@/lib/actions";
import {
  getRubrics,
  resolveProject,
  getTrace,
  getTraceEvaluations,
  getTraceRag,
  getTraces,
  hasAuthToken,
} from "@/lib/api";
import { formatCost, formatLatency, formatRelativeTime } from "@/lib/format";
import { isRagTrace } from "@/lib/rag";
import { safeErrorMessage } from "@/lib/safe-error";
import { getTraceCauseLabel, getTraceModelLabel } from "@/lib/trace-display";
import type { RagConsolidated } from "@/lib/types";

import { EvaluationStatus, GroundingStatus, evaluationVerdict } from "../trace-status";
import { TraceSteps } from "../trace-steps";
import { TraceHeaderActions } from "./trace-actions";
import { TraceConversation } from "./trace-conversation";
import { TraceEvaluations } from "./trace-evaluations";

type Tab = "conversation" | "evaluations" | "sources" | "steps" | "metadata" | "feedback";

type Props = {
  params: Promise<{ org: string; project: string; trace: string }>;
  searchParams: Promise<{
    tab?: string;
    environment?: string;
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
  if (source === "unpriced") return "sem preço — tokens registrados";
  if (source === "unknown") return "sem preço nem tokens";
  return undefined;
}

function parseTab(value: string | undefined): Tab {
  if (value === "rag" || value === "sources") return "sources";
  if (value === "waterfall" || value === "steps") return "steps";
  if (
    value === "conversation" ||
    value === "evaluations" ||
    value === "metadata" ||
    value === "feedback"
  ) {
    return value;
  }
  return "conversation";
}

export default async function TraceDetailPage({ params, searchParams }: Props) {
  const { org, project, trace } = await params;
  const qp = await searchParams;

  if (!(await hasAuthToken())) return <AuthRequiredPanel layout="main" />;

  const resolved = await resolveProject(org, project);
  const canWrite = resolved.membership?.permissions.includes("write") ?? false;
  const canDestructive = resolved.membership?.permissions.includes("destructive") ?? false;
  const detail = await getTrace(trace);
  const t = detail.trace;
  if (t.project_id !== resolved.project_id) notFound();
  const ragEnabled = isRagTrace(detail);

  const tab = parseTab(qp.tab);
  const safeQueryError = qp.error ? safeErrorMessage(qp.error, "Falha em ação.") : null;

  const conversationId =
    typeof t.metadata?.conversation_id === "string" && t.metadata.conversation_id ? (t.metadata.conversation_id as string) : null;

  const [rubricsRes, compareList, ragData, evaluations, conversation] = await Promise.all([
    getRubrics(t.project_id).catch(() => ({ data: [] })),
    getTraces({ projectId: t.project_id, limit: 12 }).catch(() => ({ data: [], next_cursor: null })),
    ragEnabled ? getTraceRag(t.id).catch(() => null as RagConsolidated | null) : Promise.resolve(null),
    getTraceEvaluations(t.id).catch(() => null),
    conversationId
      ? getTraces({ projectId: t.project_id, conversation_id: conversationId, limit: 50 }).catch(() => null)
      : Promise.resolve(null),
  ]);
  // The API lists newest first; a conversation reads oldest first.
  const conversationTurns = conversation ? [...conversation.data].reverse() : [];

  const compareCandidates = compareList.data.filter((row) => row.id !== t.id).slice(0, 10);
  const traceCause = getTraceCauseLabel(t);
  const traceModel = getTraceModelLabel(t);
  const orderedEvaluations = evaluations?.data
    .slice()
    .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at)) ?? [];
  const latestEvaluation = orderedEvaluations[0];
  const latestRubric = latestEvaluation
    ? rubricsRes.data.find((rubric) => rubric.id === latestEvaluation.rubric_id)?.slug ?? latestEvaluation.rubric_id.slice(0, 12)
    : null;
  const evaluationReason = latestEvaluation?.passed === false
    ? latestEvaluation.scores.find((score) => score.passed === false && score.reasoning)?.reasoning ?? null
    : null;
  const unsupportedClaims = ragData?.claims.filter((claim) => !claim.grounded).map((claim) => claim.text) ?? [];
  const verdict = evaluationVerdict(latestEvaluation);
  const summaryText = latestEvaluation?.passed === false
    ? { lead: `Reprovado na rubrica ${latestRubric}:`, body: evaluationReason ?? "Sem dados sobre o motivo da reprovação." }
    : latestEvaluation?.passed === true
      ? { lead: `Aprovado na rubrica ${latestRubric}.`, body: "" }
      : verdict === "partial"
        ? { lead: "Avaliação parcial.", body: "A execução não tem um veredito completo." }
        : { lead: "Sem dados de avaliação.", body: "A API não trouxe um veredito para este trace." };

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
  const environmentQuery = qp.environment === undefined ? "" : `&environment=${encodeURIComponent(qp.environment)}`;
  const tabHref = (next: Tab) => `${tabBase}?tab=${next}${environmentQuery}`;

  return (
    <div className="page">
      <header className="page-header ops-detail__header">
        <div>
          <h1 className="page-header__title ops-detail__title">
            {t.name}
            <EvaluationStatus verdict={verdict} />
            {ragEnabled ? <Badge variant="rag">RAG</Badge> : null}
            {t.redacted ? <span className="tag">redigido</span> : null}
            {detail.flags.length > 0 ? <Badge variant="warn">marcado</Badge> : null}
            {replayStatus ? (
              <Badge variant={replayBadgeVariant}>replay · {replayStatus}</Badge>
            ) : null}
          </h1>
          <div className="page-header__subtitle ops-detail__meta">
            <Copyable value={t.id} display={`${t.id.slice(0, 18)}…`} />
            <span>{t.environment}</span>
            <span>ingestão: {t.status}</span>
            {t.service ? <><span>·</span><span>{t.service}</span></> : null}
            {traceModel ? <><span>·</span><span>{traceModel}</span></> : null}
            <span>·</span>
            <span>{formatRelativeTime(t.created_at)}</span>
            {t.user_ref ? <><span>·</span><span>user: {t.user_ref}</span></> : null}
          </div>
        </div>
        <div className="page-header__actions">
          <Link href={projectHref(`/o/${org}/p/${project}`, "/traces", qp.environment)} className="btn">Voltar</Link>
          <TraceHeaderActions
            canWrite={canWrite}
            canDestructive={canDestructive}
            org={org}
            project={project}
            traceId={t.id}
            rubrics={rubricsRes.data}
            compareCandidates={compareCandidates}
            flagged={detail.flags.length > 0}
            environment={qp.environment}
          />
        </div>
      </header>

      {qp.flagged === "1" ? (
        <div className="attention" style={{ borderColor: "rgba(154,122,255,0.4)" }}>
          <div className="attention__icon"><FlagIcon size={14} /></div>
          <div>
            <div className="attention__title">Trace marcado</div>
            <div className="attention__desc">
              A marcação aparece em <Link href={tabHref("feedback")}>Feedback</Link> e na aba Marcados da lista de traces.
            </div>
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
              <Link href={projectHref(`/o/${org}/p/${project}/traces`, `/${qp.new_trace_id}`, qp.environment)} className="mono">
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
              <Link href={projectHref(`/o/${org}/p/${project}/traces`, `/${replayOf}`, qp.environment)} className="mono">
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

      <section className="card ops-detail__summary" aria-label="Resumo do trace">
        <p><strong>{summaryText.lead}</strong>{summaryText.body ? <> {summaryText.body}</> : null}</p>
      </section>

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
        <Metric label="Passos" value={`${detail.spans.length}`} />
      </section>

      {conversationId ? (
        <Card
          title="Turnos da conversa"
          subtitle={
            conversation
              ? `${conversationTurns.length} turno${conversationTurns.length === 1 ? "" : "s"}${conversation.next_cursor ? " (mostrando os 50 mais recentes)" : ""}`
              : "Falha ao carregar os outros turnos"
          }
          action={
            <Link href={`/o/${org}/p/${project}/traces?conversation_id=${encodeURIComponent(conversationId)}&environment=`} className="btn btn--sm btn--ghost">
              Ver na lista
            </Link>
          }
          className="ops-detail__turns"
        >
          <ol className="ops-detail__turn-list">
            {conversationTurns.map((turn) => (
              <li key={turn.id}>
                {turn.id === t.id ? (
                  <strong aria-current="page">{turn.name}</strong>
                ) : (
                  <Link href={projectHref(`/o/${org}/p/${project}/traces`, `/${turn.id}`, qp.environment)}>{turn.name}</Link>
                )}
                {turn.id === t.id ? <Badge variant="info">este turno</Badge> : null}
                <StatusBadge status={turn.status} />
                {turn.redacted ? <span className="tag">redigido</span> : null}
                <span className="t__faint">{formatRelativeTime(turn.created_at)}</span>
              </li>
            ))}
          </ol>
        </Card>
      ) : null}

      <nav className="tabs" aria-label="Seções do trace">
        <Link href={tabHref("conversation")} className={`tab${tab === "conversation" ? " is-active" : ""}`} aria-current={tab === "conversation" ? "page" : undefined}>
          <MessageSquare size={11} /> Conversa
        </Link>
        <Link href={tabHref("evaluations")} className={`tab${tab === "evaluations" ? " is-active" : ""}`} aria-current={tab === "evaluations" ? "page" : undefined}>
          <Target size={11} /> Avaliações
          {evaluations ? <span className="tab__count">{evaluations.data.length}</span> : null}
        </Link>
        <Link href={tabHref("steps")} className={`tab${tab === "steps" ? " is-active" : ""}`} aria-current={tab === "steps" ? "page" : undefined}>
          <Activity size={11} /> Passos
          <span className="tab__count">{detail.spans.length}</span>
        </Link>
        <Link href={tabHref("sources")} className={`tab${tab === "sources" ? " is-active" : ""}`} aria-current={tab === "sources" ? "page" : undefined}>
          <Layers size={11} /> Fontes
        </Link>
        <Link href={tabHref("metadata")} className={`tab${tab === "metadata" ? " is-active" : ""}`} aria-current={tab === "metadata" ? "page" : undefined}>
          <Terminal size={11} /> Metadata
        </Link>
        <Link href={tabHref("feedback")} className={`tab${tab === "feedback" ? " is-active" : ""}`} aria-current={tab === "feedback" ? "page" : undefined}>
          <FlagIcon size={11} /> Feedback
          <span className="tab__count">{detail.feedback.length + detail.flags.length}</span>
        </Link>
      </nav>

      {tab === "conversation" ? (
        <TraceConversation
          spans={detail.spans}
          redacted={t.redacted}
          unsupportedClaims={unsupportedClaims}
          evaluationReason={evaluationReason}
        />
      ) : null}

      {tab === "evaluations" ? (
        evaluations ? (
          <TraceEvaluations runs={evaluations.data} rubrics={rubricsRes.data} />
        ) : (
          <Card title="Avaliações" subtitle="Falha ao carregar">
            <p className="muted" style={{ margin: 0 }}>Não foi possível buscar as avaliações. Recarregue a página.</p>
          </Card>
        )
      ) : null}

      {tab === "sources" ? (
        ragEnabled && ragData ? (
          <Card
            title="Fontes"
            subtitle={`${ragData.retrieved_docs} documento${ragData.retrieved_docs === 1 ? "" : "s"} recuperado${ragData.retrieved_docs === 1 ? "" : "s"}`}
            flush
            className="ops-detail__sources"
          >
            {ragData.claims.length > 0 ? (
              <div className="table-wrap">
                <table className="t">
                  <thead>
                    <tr>
                      <th>Situação</th>
                      <th>Afirmação</th>
                      <th>Trecho usado</th>
                      <th className="t__num">Score</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ragData.claims.map((claim, index) => {
                      const chunk = ragData.claim_to_chunk.find((item) => item.claim === claim.text);
                      const citation = ragData.citations.find((item) => item.chunk === claim.cite || item.source === claim.cite);
                      const sourceText = chunk?.chunk ?? claim.cite ?? citation?.source ?? "Sem dados";
                      const score = chunk?.score ?? citation?.score;
                      return (
                        <tr key={`${claim.text}:${index}`}>
                          <td><GroundingStatus grounded={claim.grounded} /></td>
                          <td>{claim.text}</td>
                          <td className="t__mono">{sourceText}</td>
                          <td className="t__num">{score === null || score === undefined ? "Sem dados" : score.toLocaleString("pt-BR", { maximumFractionDigits: 2 })}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="t__empty">Sem dados de afirmações para verificar neste trace.</p>
            )}
            <details className="ops-detail__source-details">
              <summary>Detalhes de grounding</summary>
              <RagPanel
                retrievedDocs={ragData.retrieved_docs}
                avgScore={ragData.avg_score ?? undefined}
                groundedClaims={ragData.grounded_claims}
                hallucinationRisk={ragData.hallucination_risk}
                answerPreview={ragData.answer_preview ?? undefined}
                citations={ragData.citations.map((citation) => ({
                  rank: citation.rank,
                  title: citation.title ?? "—",
                  score: citation.score ?? undefined,
                  source: citation.source ?? undefined,
                  chunk: citation.chunk ?? undefined,
                }))}
                claims={ragData.claims.map((claim) => ({
                  text: claim.text,
                  grounded: claim.grounded,
                  cite: claim.cite ?? undefined,
                }))}
              />
            </details>
          </Card>
        ) : ragEnabled ? (
          <Card title="Fontes" subtitle="Sem dados consolidados">
            <p className="muted" style={{ margin: 0 }}>
              O endpoint <span className="mono">/v1/traces/{`{id}`}/rag</span> não retornou dados.
            </p>
          </Card>
        ) : (
          <Card title="Fontes" subtitle="Sem dados">
            <p className="muted" style={{ margin: 0 }}>Este trace não contém informações de fontes.</p>
          </Card>
        )
      ) : null}

      {tab === "steps" ? (
        <Card title="Passos" subtitle={`${detail.spans.length} passos da execução`} flush className="ops-detail__steps-panel">
          <TraceSteps
            spans={detail.spans}
            traceDurationMs={t.duration_ms}
            traceStartedAt={t.started_at}
          />
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
            subtitle={`${detail.feedback.length} feedback · ${detail.flags.length} marcaç${detail.flags.length === 1 ? "ão" : "ões"}`}
            flush
          >
            {detail.flags.map((flag) => (
              <div
                key={flag.id}
                style={{
                  padding: "10px 16px",
                  borderBottom: "1px solid var(--border-subtle)",
                  display: "flex",
                  flexDirection: "column",
                  gap: 4,
                }}
              >
                <div className="row" style={{ justifyContent: "space-between" }}>
                  <span className="row" style={{ gap: 6, fontSize: 13, color: "var(--warning)" }}>
                    <FlagIcon size={12} /> <span className="mono" style={{ fontSize: 11 }}>{flag.reason}</span>
                  </span>
                  <span className="faint mono" style={{ fontSize: 10 }}>{formatRelativeTime(flag.created_at)}</span>
                </div>
                {flag.note ? <p style={{ margin: 0, fontSize: 12, color: "var(--fg-2)" }}>{flag.note}</p> : null}
              </div>
            ))}
            {detail.feedback.length === 0 && detail.flags.length === 0 ? (
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
            {canWrite ? <form
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
            </form> : null}
          </Card>
        </div>
      ) : null}
    </div>
  );
}

