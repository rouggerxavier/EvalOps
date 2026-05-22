import Link from "next/link";
import { AlertCircle, ArrowLeftRight, GitCompareArrows } from "lucide-react";

import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { Copyable } from "@/components/ui/Copyable";
import { Metric } from "@/components/ui/Metric";
import { Waterfall } from "@/components/ui/Waterfall";
import { compareTraces, getTrace, hasAuthToken } from "@/lib/api";
import { formatCost, formatLatency, formatRelativeTime } from "@/lib/format";
import { safeErrorMessage } from "@/lib/safe-error";
import { getTraceModelLabel } from "@/lib/trace-display";
import type {
  TraceCompareResponse,
  TraceDetailResponse,
} from "@/lib/types";

type Props = {
  params: Promise<{ org: string; project: string }>;
  searchParams: Promise<{ left?: string; right?: string; error?: string }>;
};

type SpanDiffRow = {
  type: string;
  name: string;
  left_count: number;
  right_count: number;
  duration_delta_ms: number;
  error_delta: number;
  left_models: string[];
  right_models: string[];
};

type Tone = "good" | "bad" | "neutral";

function deltaTone(value: number, lowerIsBetter = true): Tone {
  if (value === 0) return "neutral";
  const negative = value < 0;
  if (lowerIsBetter) return negative ? "good" : "bad";
  return negative ? "bad" : "good";
}

function toMetricTone(tone: Tone): "up" | "down" | "neutral" {
  if (tone === "good") return "up";
  if (tone === "bad") return "down";
  return "neutral";
}

function formatDelta(value: number, format: (n: number) => string): string {
  if (value === 0) return "sem variação";
  const sign = value > 0 ? "+" : "−";
  return `${sign}${format(Math.abs(value))}`;
}

function TraceCard({
  side,
  detail,
  href,
}: {
  side: "Esquerda" | "Direita";
  detail: TraceDetailResponse;
  href: string;
}) {
  const t = detail.trace;
  const model = getTraceModelLabel(t);
  return (
    <Card
      title={`${side} · ${t.name}`}
      subtitle={`${t.environment} · ${formatRelativeTime(t.created_at)}`}
      action={
        <Link className="btn btn--sm btn--ghost" href={href}>
          Abrir trace
        </Link>
      }
    >
      <div className="col" style={{ gap: 10 }}>
        <div className="row" style={{ gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <StatusBadge status={t.status} />
          <span className="tag">{t.environment}</span>
          {model ? <span className="tag mono">{model}</span> : null}
          {t.redacted ? <span className="tag">redigido</span> : null}
        </div>
        <div className="row" style={{ gap: 10, fontFamily: "var(--font-mono)", fontSize: 11.5 }}>
          <Copyable value={t.id} display={`${t.id.slice(0, 18)}…`} />
          {t.service ? <><span>·</span><span>{t.service}</span></> : null}
          {t.user_ref ? <><span>·</span><span>user: {t.user_ref}</span></> : null}
        </div>
        <div className="kpi-grid" style={{ gridTemplateColumns: "repeat(2, minmax(0,1fr))" }}>
          <Metric label="Duração" value={formatLatency(t.duration_ms)} delta="tempo total" deltaTone="neutral" />
          <Metric label="Custo" value={formatCost(t.total_cost_usd)} delta={model ?? "—"} deltaTone="neutral" />
          <Metric
            label="Tokens"
            value={(t.total_tokens_in + t.total_tokens_out).toLocaleString("pt-BR")}
            delta={`${t.total_tokens_in}→${t.total_tokens_out}`}
            deltaTone="neutral"
          />
          <Metric
            label="Spans"
            value={`${detail.spans.length}`}
            unit={`/ ${detail.events_count}`}
            delta="capturados"
            deltaTone="neutral"
          />
        </div>
      </div>
    </Card>
  );
}

export default async function TraceComparePage({ params, searchParams }: Props) {
  const { org, project } = await params;
  const qp = await searchParams;

  if (!(await hasAuthToken())) return <AuthRequiredPanel layout="main" />;

  const baseHref = `/o/${org}/p/${project}/traces/compare`;
  const tracesHref = `/o/${org}/p/${project}/traces`;
  const leftId = qp.left?.trim() || undefined;
  const rightId = qp.right?.trim() || undefined;
  const safeQueryError = qp.error ? safeErrorMessage(qp.error, "Falha na comparação.") : null;

  let leftDetail: TraceDetailResponse | null = null;
  let rightDetail: TraceDetailResponse | null = null;
  let compare: TraceCompareResponse | null = null;
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
    } catch (err) {
      loadError = err instanceof Error ? err.message : "Falha ao carregar comparação.";
    }
  }

  const diff = (compare?.diff ?? {}) as {
    status_changed?: boolean;
    duration_delta_ms?: number;
    cost_delta_usd?: number;
    token_delta?: number;
    started_delta_seconds?: number;
    spans?: SpanDiffRow[];
  };
  const spanRows: SpanDiffRow[] = Array.isArray(diff.spans) ? diff.spans : [];

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <div className="page-header__eyebrow">
            <Link href={tracesHref} style={{ color: "var(--primary-400)" }}>
              ← Traces
            </Link>
          </div>
          <h1 className="page-header__title" style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <GitCompareArrows size={18} />
            Comparar traces
          </h1>
          <div className="page-header__subtitle">
            Diff side-by-side · KPIs, waterfall e spans agregados
          </div>
        </div>
        <div className="page-header__actions">
          {leftId && rightId ? (
            <Link
              className="btn btn--sm btn--ghost"
              href={`${baseHref}?left=${rightId}&right=${leftId}`}
              title="Inverter lados"
            >
              <ArrowLeftRight size={12} /> Inverter
            </Link>
          ) : null}
        </div>
      </header>

      {safeQueryError ? (
        <div className="attention" style={{ borderColor: "rgba(255,99,99,0.4)" }}>
          <div className="attention__icon"><AlertCircle size={14} /></div>
          <div>
            <div className="attention__title">Falha</div>
            <div className="attention__desc">{safeQueryError}</div>
          </div>
        </div>
      ) : null}

      {loadError ? (
        <div className="attention" style={{ borderColor: "rgba(255,99,99,0.4)" }}>
          <div className="attention__icon"><AlertCircle size={14} /></div>
          <div>
            <div className="attention__title">Erro ao comparar</div>
            <div className="attention__desc">{loadError}</div>
          </div>
        </div>
      ) : null}

      {!leftId || !rightId ? (
        <Card
          title="Selecione os traces"
          subtitle="Informe ?left= e ?right= ou use os atalhos abaixo"
        >
          <p className="muted" style={{ marginTop: 0, fontSize: 12 }}>
            A comparação precisa de dois traces no mesmo projeto. Abra um trace e use o
            botão <span className="mono">Comparar</span> para enfileirar este endpoint, ou
            cole os IDs em <span className="mono">{baseHref}?left=&lt;id&gt;&amp;right=&lt;id&gt;</span>.
          </p>
          <p className="muted" style={{ fontSize: 12 }}>
            <Link href={tracesHref} style={{ color: "var(--primary-400)" }}>
              Voltar para a lista de traces →
            </Link>
          </p>
        </Card>
      ) : null}

      {leftDetail && rightDetail ? (
        <section className="grid-2-eq">
          <TraceCard
            side="Esquerda"
            detail={leftDetail}
            href={`/o/${org}/p/${project}/traces/${leftDetail.trace.id}`}
          />
          <TraceCard
            side="Direita"
            detail={rightDetail}
            href={`/o/${org}/p/${project}/traces/${rightDetail.trace.id}`}
          />
        </section>
      ) : null}

      {compare ? (
        <section className="kpi-grid kpi-grid--5">
          <Metric
            label="Status"
            value={diff.status_changed ? "Mudou" : "Igual"}
            delta={`${compare.left.status} → ${compare.right.status}`}
            deltaTone={diff.status_changed ? "down" : "up"}
          />
          <Metric
            label="Δ Duração"
            value={formatDelta(diff.duration_delta_ms ?? 0, formatLatency)}
            delta={`${formatLatency(compare.left.duration_ms)} vs ${formatLatency(compare.right.duration_ms)}`}
            deltaTone={toMetricTone(deltaTone(diff.duration_delta_ms ?? 0, true))}
          />
          <Metric
            label="Δ Custo"
            value={formatDelta(diff.cost_delta_usd ?? 0, formatCost)}
            delta={`${formatCost(compare.left.total_cost_usd)} vs ${formatCost(compare.right.total_cost_usd)}`}
            deltaTone={toMetricTone(deltaTone(diff.cost_delta_usd ?? 0, true))}
          />
          <Metric
            label="Δ Tokens"
            value={formatDelta(diff.token_delta ?? 0, (n) => n.toLocaleString("pt-BR"))}
            delta="entrada + saída"
            deltaTone={toMetricTone(deltaTone(diff.token_delta ?? 0, true))}
          />
          <Metric
            label="Δ Início"
            value={
              (diff.started_delta_seconds ?? 0) === 0
                ? "0s"
                : formatDelta(diff.started_delta_seconds ?? 0, (n) => `${n}s`)
            }
            delta="right − left"
            deltaTone="neutral"
          />
        </section>
      ) : null}

      {leftDetail && rightDetail ? (
        <section className="grid-2-eq">
          <Card
            title="Waterfall esquerda"
            subtitle={`${leftDetail.spans.length} spans`}
            flush
          >
            {leftDetail.spans.length === 0 ? (
              <div className="t__empty">Nenhum span capturado.</div>
            ) : (
              <Waterfall
                spans={leftDetail.spans}
                traceDurationMs={leftDetail.trace.duration_ms}
                traceStartedAt={leftDetail.trace.started_at}
              />
            )}
          </Card>
          <Card
            title="Waterfall direita"
            subtitle={`${rightDetail.spans.length} spans`}
            flush
          >
            {rightDetail.spans.length === 0 ? (
              <div className="t__empty">Nenhum span capturado.</div>
            ) : (
              <Waterfall
                spans={rightDetail.spans}
                traceDurationMs={rightDetail.trace.duration_ms}
                traceStartedAt={rightDetail.trace.started_at}
              />
            )}
          </Card>
        </section>
      ) : null}

      {compare ? (
        <Card
          title="Spans agregados"
          subtitle={`${spanRows.length} grupo${spanRows.length === 1 ? "" : "s"} (type + name)`}
          flush
        >
          {spanRows.length === 0 ? (
            <div className="t__empty">Sem spans para comparar.</div>
          ) : (
            <div className="table-wrap">
              <table className="t">
                <thead>
                  <tr>
                    <th>Tipo</th>
                    <th>Nome</th>
                    <th className="t__num">Esq.</th>
                    <th className="t__num">Dir.</th>
                    <th className="t__num">Δ Duração</th>
                    <th className="t__num">Δ Erros</th>
                    <th>Modelos</th>
                  </tr>
                </thead>
                <tbody>
                  {spanRows.map((row) => {
                    const durTone = deltaTone(row.duration_delta_ms, true);
                    const errTone = deltaTone(row.error_delta, true);
                    const models = Array.from(new Set([...row.left_models, ...row.right_models]));
                    return (
                      <tr key={`${row.type}:${row.name}`}>
                        <td className="t__mono">
                          <Badge variant={row.type === "llm" ? "info" : row.type === "eval" ? "eval" : row.type === "retrieval" ? "rag" : "ok"}>
                            {row.type}
                          </Badge>
                        </td>
                        <td className="t__name">{row.name}</td>
                        <td className="t__num">{row.left_count}</td>
                        <td className="t__num">{row.right_count}</td>
                        <td
                          className="t__num mono"
                          style={{
                            color:
                              durTone === "good"
                                ? "var(--success)"
                                : durTone === "bad"
                                ? "var(--danger)"
                                : "var(--fg-2)",
                          }}
                        >
                          {row.duration_delta_ms === 0 ? "—" : formatDelta(row.duration_delta_ms, formatLatency)}
                        </td>
                        <td
                          className="t__num mono"
                          style={{
                            color:
                              errTone === "good"
                                ? "var(--success)"
                                : errTone === "bad"
                                ? "var(--danger)"
                                : "var(--fg-2)",
                          }}
                        >
                          {row.error_delta === 0 ? "—" : (row.error_delta > 0 ? "+" : "") + row.error_delta}
                        </td>
                        <td className="t__mono faint">{models.length === 0 ? "—" : models.join(", ")}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      ) : null}

    </div>
  );
}
