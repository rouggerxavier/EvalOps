import Link from "next/link";
import { Activity, AlertCircle, ArrowRight, Clock3, Coins, RefreshCw, Target } from "lucide-react";

import { QualityGateCard } from "@/components/QualityGateCard";
import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { AreaChart, Card, Metric } from "@/components/ui/index";
import {
  getAttention,
  getOverview,
  getQualityGateStatus,
  getRubricReport,
  getRubrics,
  getSdkStatus,
  getTraces,
  hasAuthToken,
  resolveProject,
} from "@/lib/api";
import { getActiveEnvironment } from "@/lib/active-env";
import type { RubricReport, Trace } from "@/lib/types";

import { EvaluateHeaderButton, OverviewMobileFilters, WindowSelect } from "./overview-actions";

type Window = "24h" | "7d" | "30d";
type Props = {
  params: Promise<{ org: string; project: string }>;
  searchParams: Promise<{ environment?: string; window?: string }>;
};

const CAUSE_LABELS: Record<string, string> = {
  schema_mismatch: "Incompatibilidade de schema",
  timeout: "Timeout",
  partial_trace: "Trace parcial",
  trace_error: "Erro no trace",
};

function fmtInteger(value: number): string {
  return new Intl.NumberFormat("pt-BR").format(value);
}

function fmtCompact(value: number): string {
  return new Intl.NumberFormat("pt-BR", { notation: "compact", maximumFractionDigits: 1 }).format(value);
}

function fmtPercent(value: number): string {
  return new Intl.NumberFormat("pt-BR", { style: "percent", maximumFractionDigits: 1 }).format(value);
}

function fmtCost(value: number): string {
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(value);
}

function fmtLatency(value: number): string {
  return value < 1000
    ? `${fmtInteger(Math.round(value))} ms`
    : `${new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 }).format(value / 1000)} s`;
}

function fmtDate(value: string): string {
  return new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "short", timeZone: "UTC" }).format(new Date(value));
}

function fmtTime(value: string): string {
  return new Intl.DateTimeFormat("pt-BR", { hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}

function fmtRelativeTime(value: string): string {
  const minutes = Math.max(0, Math.round((Date.now() - new Date(value).getTime()) / 60000));
  if (minutes < 1) return "agora";
  if (minutes < 60) return `há ${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `há ${hours} h`;
  return `há ${Math.round(hours / 24)} d`;
}

function parseWindow(value: string | undefined): Window {
  if (value === "7d" || value === "30d") return value;
  return "24h";
}

function aggregateApproval(reports: Array<{ rubric: { id: string; slug: string }; report: RubricReport | null }>) {
  const passed = reports.reduce((sum, item) => sum + (item.report?.totals.passed ?? 0), 0);
  const failed = reports.reduce((sum, item) => sum + (item.report?.totals.failed ?? 0), 0);
  const verdicts = passed + failed;
  const byDay = new Map<string, { passed: number; verdicts: number }>();

  for (const { report } of reports) {
    for (const point of report?.by_day ?? []) {
      const verdictsForDay = point.passed + point.failed;
      if (verdictsForDay === 0) continue;
      const aggregate = byDay.get(point.day) ?? { passed: 0, verdicts: 0 };
      aggregate.passed += point.passed;
      aggregate.verdicts += verdictsForDay;
      byDay.set(point.day, aggregate);
    }
  }

  return {
    passed,
    verdicts,
    rate: verdicts > 0 ? passed / verdicts : null,
    trend: [...byDay.entries()]
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([day, result]) => ({ label: fmtDate(day), value: result.passed / result.verdicts })),
  };
}

function TraceStatus({ status }: { status: "error" | "partial" }) {
  const label = status === "partial" ? "Parcial" : "Erro";
  return (
    <span className={`ops-status ops-status--${status === "partial" ? "partial" : "rejected"}`}>
      <AlertCircle size={13} aria-hidden="true" />{label}
    </span>
  );
}

export default async function ProjectOverviewPage({ params, searchParams }: Props) {
  const { org, project } = await params;
  const query = await searchParams;
  const environment = await getActiveEnvironment(query.environment);
  const window_ = parseWindow(query.window);

  if (!(await hasAuthToken())) return <AuthRequiredPanel layout="main" />;

  const resolved = await resolveProject(org, project);
  const projectId = resolved.project_id;
  const [overview, attention, sdk, rubricsRes, flaggedRes, gate] = await Promise.all([
    getOverview(projectId, environment, window_),
    getAttention(projectId, environment).catch(() => null),
    getSdkStatus(projectId).catch(() => null),
    getRubrics(projectId).catch(() => ({ data: [] })),
    getTraces({ projectId, limit: 25, status: "error,partial", environment }).catch(() => ({ data: [] as Trace[], next_cursor: null })),
    getQualityGateStatus(projectId, environment, window_).catch(() => null),
  ]);

  const rubricReports = await Promise.all(
    rubricsRes.data.map(async (rubric) => ({
      rubric,
      report: await getRubricReport(projectId, rubric.id, window_, environment).catch(() => null),
    })),
  );
  const approval = aggregateApproval(rubricReports);
  const rubrics = rubricsRes.data.map((rubric) => ({ id: rubric.id, slug: rubric.slug, current_version: rubric.current_version }));
  const flaggedTraces = flaggedRes.data;
  const traceById = new Map(flaggedTraces.map((trace) => [trace.id, trace]));
  const attentionItems = attention?.items.slice(0, 3) ?? [];
  const environmentQuery = `environment=${encodeURIComponent(environment ?? "")}`;
  const tracesHref = `/o/${org}/p/${project}/traces?${environmentQuery}`;
  const evaluationsHref = `/o/${org}/p/${project}/evaluations?${environmentQuery}`;
  const exportHref = `/o/${org}/p/${project}/exports`;
  const refreshHref = `/o/${org}/p/${project}?window=${window_}&${environmentQuery}`;
  const actionsCtx = {
    org,
    project,
    projectId,
    environment,
    rubrics,
    candidateTraces: flaggedTraces.slice(0, 4).map((trace) => ({ id: trace.id, name: trace.name })),
  };
  const modelBreakdown = overview.model_breakdown;
  const totalCalls = modelBreakdown.reduce((sum, model) => sum + model.calls, 0);
  const feedback = overview.human_feedback;
  const thumbCount = feedback.thumbs_up + feedback.thumbs_down;
  const traceSpark = overview.cost_by_day.slice(-14).map((point) => point.traces);
  const costSpark = overview.cost_by_day.slice(-14).map((point) => point.cost_usd);
  const windowLabel = window_ === "24h" ? "últimas 24 horas" : window_ === "7d" ? "últimos 7 dias" : "últimos 30 dias";
  const environmentLabel = environment === "prod" ? "Produção" : environment === "staging" ? "Staging" : environment === "dev" ? "Dev" : "Todos os ambientes";

  return (
    <main className="page ops-page ops-overview">
      <OverviewMobileFilters org={org} project={project} current={window_} environment={environment} />

      <header className="ops-overview__header">
        <div className="ops-overview__header-copy">
          <h1>Visão geral</h1>
          <p>{resolved.project_name} · {environmentLabel} · {windowLabel}</p>
        </div>
        <div className="ops-overview__actions">
          <WindowSelect org={org} project={project} current={window_} environment={environment} />
          <Link href={exportHref} className="btn btn--sm">Exportar</Link>
          <EvaluateHeaderButton ctx={actionsCtx} />
        </div>
      </header>


      <section className="ops-overview__summary" aria-live="polite">
        <span className={`ops-overview__summary-mark${attention?.count ? " ops-overview__summary-mark--attention" : ""}`}>
          {attention?.count ? <AlertCircle size={14} aria-hidden="true" /> : <Target size={14} aria-hidden="true" />}
          {attention?.count ? "Atenção" : "Resumo"}
        </span>
        <strong>
          {approval.verdicts > 0
            ? `${fmtInteger(approval.passed)} de ${fmtInteger(approval.verdicts)} avaliações concluídas foram aprovadas.`
            : "Sem dados de aprovação no período selecionado."}
        </strong>
        {attention?.count ? (
          <span>{attention.count >= 25 ? "25+" : fmtInteger(attention.count)} traces com erro ou parciais nas últimas 24h · {environmentLabel}.</span>
        ) : attention ? (
          <span>Nenhum trace com erro ou parcial nas últimas 24h.</span>
        ) : (
          <span>Contagem de atenção indisponível.</span>
        )}
      </section>

      <QualityGateCard gate={gate} settingsHref={`/o/${org}/p/${project}/settings#quality-gate`} />

      <section className="kpi-grid kpi-grid--5 ops-overview__metrics" aria-label="Indicadores do período">
        <Metric label="Taxa de aprovação" icon={<Target size={13} aria-hidden="true" />} value={approval.rate === null ? "Sem dados" : fmtPercent(approval.rate)} />
        <Metric label="Traces" icon={<Activity size={13} aria-hidden="true" />} value={fmtCompact(overview.kpis.traces)} spark={traceSpark.length > 1 ? traceSpark : undefined} />
        <Metric label="Latência p95" icon={<Clock3 size={13} aria-hidden="true" />} value={fmtLatency(overview.kpis.latency_p95_ms)} />
        <Metric label="Custo" icon={<Coins size={13} aria-hidden="true" />} value={fmtCost(overview.kpis.cost_usd)} spark={costSpark.length > 1 ? costSpark : undefined} />
        <Metric label="Taxa de erro" icon={<AlertCircle size={13} aria-hidden="true" />} value={fmtPercent(overview.kpis.error_rate)} />
      </section>

      <Card title="Feedback humano" subtitle={`Feedback dos traces na janela · ${windowLabel} · ${environmentLabel}`}>
        <div className="ops-overview__rubrics">
          <div className="ops-overview__rubric-head"><span>Envios</span><strong>{fmtInteger(feedback.feedback_count)}</strong></div>
          <div className="ops-overview__rubric-head"><span>Traces com feedback</span><strong>{fmtInteger(feedback.trace_count)} de {fmtInteger(overview.kpis.traces)}</strong></div>
          <div className="ops-overview__rubric-head"><span>Positivos</span><strong>{thumbCount > 0 ? fmtPercent(feedback.thumbs_up / thumbCount) : "Sem dados"} · n={fmtInteger(thumbCount)}</strong></div>
          <div className="ops-overview__rubric-head"><span>Negativos</span><strong>{fmtInteger(feedback.thumbs_down)}</strong></div>
          <div className="ops-overview__rubric-head"><span>Nota média</span><strong>{feedback.avg_rating === null ? "Sem dados" : `${new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 }).format(feedback.avg_rating)} / 5`} · n={fmtInteger(feedback.rating_count)}</strong></div>
        </div>
        <p className="ops-overview__table-note">Cada envio conta. Feedback posterior atualiza os resultados.</p>
      </Card>

      <section className="ops-overview__grid ops-overview__grid--top">
        <Card
          title="Precisa de atenção"
          subtitle={`últimas 24 horas · ${environmentLabel}`}
          action={<Link href={tracesHref} className="ops-overview__text-link">Ver todos os traces</Link>}
          flush
        >
          {attention === null ? (
            <div className="ops-overview__empty">
              <strong>Não foi possível carregar os traces que precisam de atenção.</strong>
              <Link href={tracesHref}>Abrir traces <ArrowRight size={12} /></Link>
            </div>
          ) : attentionItems.length === 0 ? (
            <div className="ops-overview__empty">
              <strong>Nenhum trace com erro ou parcial nas últimas 24 horas.</strong>
              <Link href={tracesHref}>Abrir traces <ArrowRight size={12} /></Link>
            </div>
          ) : (
            <div className="table-wrap ops-overview__table-wrap">
              <table className="t ops-overview__attention-table">
                <thead>
                  <tr><th>Situação</th><th>Assunto</th><th>Serviço</th><th>Trace</th><th>Desde</th></tr>
                </thead>
                <tbody>
                  {attentionItems.map((item) => {
                    const trace = traceById.get(item.trace_id);
                    const status = item.cause === "partial_trace" || trace?.status === "partial" ? "partial" : "error";
                    const cause = item.cause;
                    const label = CAUSE_LABELS[cause] ?? cause.replaceAll("_", " ");
                    return (
                      <tr key={item.trace_id}>
                        <td><TraceStatus status={status} /></td>
                        <td>
                          <span className="ops-overview__attention-title">{label}</span>
                          <span className="ops-overview__attention-note">{trace?.name ?? "Trace listado pela API"}</span>
                        </td>
                        <td className="t__mono">{item.service ?? "—"}</td>
                        <td>
                          <Link className="ops-overview__trace-link" href={`/o/${org}/p/${project}/traces/${item.trace_id}?${environmentQuery}`}>
                            {item.trace_id.slice(0, 10)}
                          </Link>
                        </td>
                        <td className="t__faint">{fmtTime(item.at)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {attention.count >= 25 ? <p className="ops-overview__table-note">A API lista no máximo 25 traces nesta seção.</p> : null}
            </div>
          )}
        </Card>

        <Card title="Aprovação por rubrica" action={<Link href={evaluationsHref} className="ops-overview__text-link">Detalhes</Link>}>
          {rubricReports.length === 0 ? (
            <div className="ops-overview__empty ops-overview__empty--compact">
              <strong>Sem dados de aprovação.</strong>
              <Link href={`/o/${org}/p/${project}/rubrics`}>Ver rubricas <ArrowRight size={12} /></Link>
            </div>
          ) : (
            <div className="ops-overview__rubrics">
              {rubricReports.slice(0, 5).map(({ rubric, report }) => {
                const rate = report?.totals.pass_rate ?? null;
                const results = (report?.totals.passed ?? 0) + (report?.totals.failed ?? 0);
                return (
                  <div className="ops-overview__rubric" key={rubric.id}>
                    <div className="ops-overview__rubric-head">
                      <span>{rubric.slug}</span>
                      <strong>{rate === null ? "Sem dados" : fmtPercent(rate)}</strong>
                    </div>
                    <div className="ops-overview__progress" role="progressbar" aria-label={`Taxa de aprovação de ${rubric.slug}`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={rate === null ? 0 : Math.round(rate * 100)} aria-valuetext={rate === null ? "Sem dados" : fmtPercent(rate)}>
                      <span className={rate !== null && rate < 0.7 ? "is-low" : ""} style={{ width: `${rate === null ? 0 : Math.round(rate * 100)}%` }} />
                    </div>
                    <span className="ops-overview__rubric-meta">{results > 0 ? `${fmtInteger(results)} avaliações concluídas` : "Sem dados no período"}</span>
                  </div>
                );
              })}
            </div>
          )}
        </Card>
      </section>

      <section className="ops-overview__grid ops-overview__grid--bottom">
        <Card title="Taxa de aprovação" subtitle={`${windowLabel} · resultados concluídos`}>
          {approval.trend.length > 0 ? (
            <AreaChart data={approval.trend} color="var(--ops-action)" height={180} />
          ) : (
            <div className="ops-overview__empty">
              <strong>Sem dados para mostrar a evolução da taxa de aprovação.</strong>
              <Link href={evaluationsHref}>Abrir avaliações <ArrowRight size={12} /></Link>
            </div>
          )}
        </Card>

        <Card title="Custo por modelo" flush>
          <div className="table-wrap ops-overview__table-wrap">
            <table className="t ops-overview__model-table">
              <thead><tr><th>Modelo</th><th className="t__num">Chamadas</th><th className="t__num">Custo</th></tr></thead>
              <tbody>
                {modelBreakdown.length === 0 ? (
                  <tr><td colSpan={3} className="t__empty">Sem dados de chamadas por modelo.</td></tr>
                ) : modelBreakdown.map((model) => (
                  <tr key={`${model.provider}-${model.model}`}>
                    <td>
                      <span className="ops-overview__model-name">{model.model ?? "Sem dados"}</span>
                      <span className="ops-overview__model-provider">{model.provider ?? "Sem dados"}</span>
                    </td>
                    <td className="t__num">{fmtInteger(model.calls)}</td>
                    <td className="t__num">{fmtCost(model.cost_usd)}</td>
                  </tr>
                ))}
              </tbody>
              {totalCalls > 0 ? <caption>{fmtInteger(totalCalls)} chamadas na janela selecionada</caption> : null}
            </table>
          </div>
        </Card>
      </section>

      <footer className="ops-overview__footer">
        <span>
          SDK · {sdk ? `${fmtInteger(Math.round(sdk.spans_per_minute))} spans/min · último evento ${sdk.last_event_at ? fmtRelativeTime(sdk.last_event_at) : "sem dados"} · todos os ambientes` : "Sem dados de ingestão na última hora."}
        </span>
        <span className="ops-overview__footer-window">{environmentLabel} · {windowLabel}</span>
        <Link href={refreshHref} aria-label="Atualizar visão geral" title="Atualizar visão geral"><RefreshCw size={13} /></Link>
      </footer>
    </main>
  );
}
