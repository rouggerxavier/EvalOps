import Link from "next/link";
import { AlertCircle, ArrowLeftRight, GitCompareArrows } from "lucide-react";

import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { projectHref } from "@/components/app-shell-nav";
import { Card } from "@/components/ui/Card";
import { ScoreCell } from "@/components/ui/ScoreCell";
import { compareTraces, getTrace, getTraceEvaluations, getTraceRag, hasAuthToken } from "@/lib/api";
import { formatCost, formatLatency, formatRelativeTime } from "@/lib/format";
import { safeErrorMessage } from "@/lib/safe-error";
import { isRagTrace } from "@/lib/rag";
import type { EvaluationRun, RagConsolidated, TraceCompareResponse, TraceDetailResponse } from "@/lib/types";

import { evaluationVerdict, EvaluationStatus, type EvaluationVerdict } from "../trace-status";
import { TraceAnswer } from "../trace-answer";
import { TraceSteps } from "../trace-steps";

type Props = {
  params: Promise<{ org: string; project: string }>;
  searchParams: Promise<{ left?: string; right?: string; error?: string; environment?: string }>;
};

type Tone = "good" | "bad" | "neutral";

function latestEvaluation(runs: EvaluationRun[] | null): EvaluationRun | undefined {
  return runs?.slice().sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))[0];
}

function promptVersion(detail: TraceDetailResponse): string | null {
  return [...detail.spans].reverse().find((span) => span.prompt_version_ref)?.prompt_version_ref ?? null;
}

function signed(value: number, formatter: (value: number) => string): string {
  if (value === 0) return formatter(0);
  return `${value > 0 ? "+" : "−"}${formatter(Math.abs(value))}`;
}

function deltaTone(value: number, lowerIsBetter = true): Tone {
  if (value === 0) return "neutral";
  return (value < 0) === lowerIsBetter ? "good" : "bad";
}

function toneClass(tone: Tone): string {
  return `ops-compare__difference ops-compare__difference--${tone}`;
}

function statusDifference(left: EvaluationVerdict | null, right: EvaluationVerdict | null): { label: string; tone: Tone } {
  if (!left || !right || left === "unknown" || right === "unknown") return { label: "Sem dados", tone: "neutral" };
  if (left === right) return { label: "Igual", tone: "neutral" };
  if (left === "approved" && right === "rejected") return { label: "Piorou", tone: "bad" };
  if (left === "rejected" && right === "approved") return { label: "Melhorou", tone: "good" };
  return { label: "Mudou", tone: "neutral" };
}

function evaluationReason(run: EvaluationRun | undefined): string | null {
  if (run?.passed !== false) return null;
  return run.scores.find((score) => score.passed === false && score.reasoning)?.reasoning ?? null;
}

export default async function TraceComparePage({ params, searchParams }: Props) {
  const { org, project } = await params;
  const qp = await searchParams;

  if (!(await hasAuthToken())) return <AuthRequiredPanel layout="main" />;

  const baseHref = `/o/${org}/p/${project}/traces/compare`;
  const tracesHref = projectHref(`/o/${org}/p/${project}`, "/traces", qp.environment);
  const environmentQuery = qp.environment === undefined ? "" : `&environment=${encodeURIComponent(qp.environment)}`;
  const leftId = qp.left?.trim() || undefined;
  const rightId = qp.right?.trim() || undefined;
  const safeQueryError = qp.error ? safeErrorMessage(qp.error, "Falha na comparação.") : null;

  let leftDetail: TraceDetailResponse | null = null;
  let rightDetail: TraceDetailResponse | null = null;
  let compare: TraceCompareResponse | null = null;
  let leftRuns: EvaluationRun[] | null = null;
  let rightRuns: EvaluationRun[] | null = null;
  let leftRag: RagConsolidated | null = null;
  let rightRag: RagConsolidated | null = null;
  let loadError: string | null = null;

  if (leftId && rightId) {
    try {
      const [leftRes, rightRes, cmpRes] = await Promise.all([
        getTrace(leftId),
        getTrace(rightId),
        compareTraces({ left_trace_id: leftId, right_trace_id: rightId }),
      ]);
      leftDetail = leftRes;
      rightDetail = rightRes;
      compare = cmpRes;
      const [leftEvalRes, rightEvalRes, leftRagRes, rightRagRes] = await Promise.all([
        getTraceEvaluations(leftId).catch(() => null),
        getTraceEvaluations(rightId).catch(() => null),
        isRagTrace(leftRes) ? getTraceRag(leftId).catch(() => null) : Promise.resolve(null),
        isRagTrace(rightRes) ? getTraceRag(rightId).catch(() => null) : Promise.resolve(null),
      ]);
      leftRuns = leftEvalRes?.data ?? null;
      rightRuns = rightEvalRes?.data ?? null;
      leftRag = leftRagRes;
      rightRag = rightRagRes;
    } catch (err) {
      loadError = err instanceof Error ? err.message : "Falha ao carregar comparação.";
    }
  }

  const leftRun = latestEvaluation(leftRuns);
  const rightRun = latestEvaluation(rightRuns);
  const leftVerdict = evaluationVerdict(leftRun);
  const rightVerdict = evaluationVerdict(rightRun);
  const leftVersion = leftDetail ? promptVersion(leftDetail) : null;
  const rightVersion = rightDetail ? promptVersion(rightDetail) : null;
  const diff = (compare?.diff ?? {}) as {
    duration_delta_ms?: number;
    cost_delta_usd?: number;
    token_delta?: number;
  };
  const durationDelta = typeof diff.duration_delta_ms === "number" ? diff.duration_delta_ms : null;
  const costDelta = typeof diff.cost_delta_usd === "number" ? diff.cost_delta_usd : null;
  const tokenDelta = typeof diff.token_delta === "number" ? diff.token_delta : null;
  const scoreDelta = leftRun?.aggregate_score !== null && leftRun?.aggregate_score !== undefined && rightRun?.aggregate_score !== null && rightRun?.aggregate_score !== undefined
    ? rightRun.aggregate_score - leftRun.aggregate_score
    : null;
  const promptChanged = leftVersion && rightVersion ? leftVersion !== rightVersion : null;
  const statusDiff = statusDifference(leftVerdict, rightVerdict);
  const unsupportedLeft = leftRag?.claims.filter((claim) => !claim.grounded).map((claim) => claim.text) ?? [];
  const unsupportedRight = rightRag?.claims.filter((claim) => !claim.grounded).map((claim) => claim.text) ?? [];

  const summaryText = (() => {
    if (!compare) return null;
    const costText = costDelta === null
      ? "Custo sem dados de diferença."
      : costDelta < 0
        ? `A execução B custou ${formatCost(Math.abs(costDelta))} menos.`
        : costDelta > 0
          ? `A execução B custou ${formatCost(costDelta)} a mais.`
          : "As duas execuções tiveram o mesmo custo.";
    const verdictText = rightVerdict === "approved"
      ? "A execução B foi aprovada."
      : rightVerdict === "rejected"
        ? "A execução B foi reprovada."
        : rightVerdict === "partial"
          ? "A avaliação da execução B ficou parcial."
          : "Veredito da execução B: sem dados.";
    const changedText = promptChanged === null
      ? "Versão do prompt: sem dados."
      : promptChanged
        ? "A versão do prompt mudou."
        : "A versão do prompt não mudou.";
    const reason = evaluationReason(rightRun);
    return [costText, verdictText, changedText, reason ? `Motivo registrado: ${reason}` : null].filter(Boolean).join(" ");
  })();

  return (
    <div className="page">
      <header className="page-header ops-compare__header">
        <div>
          <h1 className="page-header__title"><GitCompareArrows size={18} /> Comparar traces</h1>
          <div className="page-header__subtitle">
            {leftDetail && rightDetail
              ? `Duas execuções do fluxo ${leftDetail.trace.name}`
              : "Compare duas execuções do mesmo projeto"}
          </div>
        </div>
        <div className="page-header__actions">
          <Link className="btn" href={tracesHref}>Voltar</Link>
          {leftId && rightId ? (
            <Link className="btn" href={`${baseHref}?left=${encodeURIComponent(rightId)}&right=${encodeURIComponent(leftId)}${environmentQuery}`} title="Inverter lados">
              <ArrowLeftRight size={14} /> Inverter lados
            </Link>
          ) : null}
        </div>
      </header>

      {safeQueryError ? (
        <div className="attention" role="status">
          <div className="attention__icon"><AlertCircle size={14} /></div>
          <div><div className="attention__title">Falha</div><div className="attention__desc">{safeQueryError}</div></div>
        </div>
      ) : null}

      {loadError ? (
        <div className="attention" role="alert">
          <div className="attention__icon"><AlertCircle size={14} /></div>
          <div><div className="attention__title">Erro ao comparar</div><div className="attention__desc">{loadError}</div></div>
        </div>
      ) : null}

      {!leftId || !rightId ? (
        <Card title="Selecione os traces" subtitle="Informe ?left= e ?right= ou selecione dois traces na lista">
          <p className="muted" style={{ marginTop: 0, fontSize: 12 }}>
            A comparação precisa de dois traces do mesmo projeto. Use as caixas de seleção na lista de traces.
          </p>
          <Link href={tracesHref} className="btn">Voltar para a lista de traces</Link>
        </Card>
      ) : null}

      {compare && leftDetail && rightDetail && summaryText ? (
        <>
          <section className="card ops-compare__summary" aria-label="Resumo da comparação">
            <p>{summaryText}</p>
          </section>

          <Card flush className="ops-compare__table">
            <div className="table-wrap">
              <table className="t">
                <thead>
                  <tr>
                    <th>Indicador</th>
                    <th>
                      <Link href={projectHref(`/o/${org}/p/${project}/traces`, `/${leftDetail.trace.id}`, qp.environment)}>
                        A · <span className="t__mono">{leftDetail.trace.id}</span>
                      </Link>
                    </th>
                    <th>
                      <Link href={projectHref(`/o/${org}/p/${project}/traces`, `/${rightDetail.trace.id}`, qp.environment)}>
                        B · <span className="t__mono">{rightDetail.trace.id}</span>
                      </Link>
                    </th>
                    <th className="t__num">Diferença de B</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>Situação</td>
                    <td><EvaluationStatus verdict={leftVerdict} /></td>
                    <td><EvaluationStatus verdict={rightVerdict} /></td>
                    <td className={toneClass(statusDiff.tone)}>{statusDiff.label}</td>
                  </tr>
                  <tr>
                    <td>Score</td>
                    <td>{leftRun?.aggregate_score == null ? "Sem dados" : <ScoreCell value={leftRun.aggregate_score} />}</td>
                    <td>{rightRun?.aggregate_score == null ? "Sem dados" : <ScoreCell value={rightRun.aggregate_score} />}</td>
                    <td className={toneClass(scoreDelta === null ? "neutral" : deltaTone(scoreDelta, false))}>
                      {scoreDelta === null ? "Sem dados" : signed(scoreDelta, (value) => value.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }))}
                    </td>
                  </tr>
                  <tr>
                    <td>Duração</td>
                    <td>{formatLatency(leftDetail.trace.duration_ms)}</td>
                    <td>{formatLatency(rightDetail.trace.duration_ms)}</td>
                    <td className={toneClass(durationDelta === null ? "neutral" : deltaTone(durationDelta))}>
                      {durationDelta === null ? "Sem dados" : signed(durationDelta, formatLatency)}
                    </td>
                  </tr>
                  <tr>
                    <td>Custo</td>
                    <td>{formatCost(leftDetail.trace.total_cost_usd)}</td>
                    <td>{formatCost(rightDetail.trace.total_cost_usd)}</td>
                    <td className={toneClass(costDelta === null ? "neutral" : deltaTone(costDelta))}>
                      {costDelta === null ? "Sem dados" : signed(costDelta, formatCost)}
                    </td>
                  </tr>
                  <tr>
                    <td>Tokens</td>
                    <td>{(leftDetail.trace.total_tokens_in + leftDetail.trace.total_tokens_out).toLocaleString("pt-BR")}</td>
                    <td>{(rightDetail.trace.total_tokens_in + rightDetail.trace.total_tokens_out).toLocaleString("pt-BR")}</td>
                    <td className={toneClass("neutral")}>
                      {tokenDelta === null ? "Sem dados" : signed(tokenDelta, (value) => value.toLocaleString("pt-BR"))}
                    </td>
                  </tr>
                  <tr>
                    <td>Versão do prompt</td>
                    <td className="t__mono">{leftVersion ?? "Sem dados"}</td>
                    <td className="t__mono">{rightVersion ?? "Sem dados"}</td>
                    <td className={toneClass("neutral")}>
                      {promptChanged === null ? "Sem dados" : promptChanged ? "Mudou" : "Igual"}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </Card>

          <div className="grid-2-eq ops-compare__responses">
            <Card
              title="Resposta de A"
              action={<EvaluationStatus verdict={leftVerdict} />}
              className="ops-compare__answer"
            >
              <TraceAnswer spans={leftDetail.spans} unsupportedClaims={unsupportedLeft} redacted={leftDetail.trace.redacted} />
            </Card>
            <Card
              title="Resposta de B"
              action={<EvaluationStatus verdict={rightVerdict} />}
              className="ops-compare__answer"
            >
              <TraceAnswer spans={rightDetail.spans} unsupportedClaims={unsupportedRight} redacted={rightDetail.trace.redacted} />
            </Card>
          </div>

          <div className="grid-2-eq ops-compare__steps">
            <Card title="Passos de A" action={<span>{formatLatency(leftDetail.trace.duration_ms)}</span>} className="ops-compare__steps-panel">
              <TraceSteps spans={leftDetail.spans} traceDurationMs={leftDetail.trace.duration_ms} traceStartedAt={leftDetail.trace.started_at} />
            </Card>
            <Card title="Passos de B" action={<span>{formatLatency(rightDetail.trace.duration_ms)}</span>} className="ops-compare__steps-panel">
              <TraceSteps spans={rightDetail.spans} traceDurationMs={rightDetail.trace.duration_ms} traceStartedAt={rightDetail.trace.started_at} />
            </Card>
          </div>

          <p className="ops-compare__meta">
            A · {leftDetail.trace.environment} · {formatRelativeTime(leftDetail.trace.created_at)}
            <span> · </span>
            B · {rightDetail.trace.environment} · {formatRelativeTime(rightDetail.trace.created_at)}
            {leftRuns === null || rightRuns === null ? <span> · avaliações: sem dados</span> : null}
          </p>
        </>
      ) : null}
    </div>
  );
}
