import Link from "next/link";
import type { ReactNode } from "react";
import {
  Activity,
  AlertCircle,
  ArrowRight,
  BarChart3,
  CheckCircle2,
  Clock,
  Coins,
  Copy,
  Database,
  Download,
  FileText,
  KeyRound,
  ListChecks,
  Play,
  RefreshCw,
  Sparkles,
  Target,
} from "lucide-react";

import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import {
  getOverview,
  getProjectEvaluations,
  getRubrics,
  getTraces,
  hasAuthToken,
  resolveProject,
} from "@/lib/api";
import { getApiBaseUrl } from "@/lib/config";
import { formatCost, formatLatency, formatPercent } from "@/lib/format";
import { getTraceCauseLabel, getTraceModelLabel } from "@/lib/trace-display";
import type { EvaluationRun, OverviewResponse, Rubric, Trace } from "@/lib/types";

function apiRoot(): string {
  try {
    const base = getApiBaseUrl();
    return base.endsWith("/v1") ? base.slice(0, -3) : base;
  } catch {
    return "#";
  }
}

type Props = {
  params: Promise<{ org: string; project: string }>;
  searchParams: Promise<{ environment?: string }>;
};

type ChartPoint = { label: string; cost: number; traces: number };
type BadgeVariant = "default" | "ok" | "warn" | "err" | "info" | "eval";

function fmtNumber(n: number): string {
  return new Intl.NumberFormat("pt-BR", {
    notation: n >= 10000 ? "compact" : "standard",
    maximumFractionDigits: 1,
  }).format(n);
}

function fmtInteger(n: number): string {
  return new Intl.NumberFormat("pt-BR").format(n);
}

function fmtShortDate(value: string): string {
  return new Date(value).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", timeZone: "UTC" });
}

function fmtScore(value: number | null): string {
  return value === null ? "Sem score" : value.toFixed(2);
}

function timeAgo(value: string): string {
  const delta = Date.now() - new Date(value).getTime();
  const minutes = Math.max(0, Math.round(delta / 60000));
  if (minutes < 1) return "agora";
  if (minutes < 60) return `${minutes}min atras`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h atras`;
  const days = Math.round(hours / 24);
  return `${days}d atras`;
}

function statusLabel(status: string): string {
  if (status === "ok" || status === "success" || status === "completed") return "ok";
  if (status === "partial" || status === "queued" || status === "running") return "parcial";
  if (status === "error" || status === "failed") return "erro";
  return status;
}

function statusVariant(status: string): BadgeVariant {
  if (status === "ok" || status === "success" || status === "completed") return "ok";
  if (status === "partial" || status === "queued" || status === "running") return "warn";
  if (status === "error" || status === "failed") return "err";
  return "default";
}

function runStatusLabel(run: EvaluationRun): string {
  if (run.passed === true) return "passou";
  if (run.passed === false) return "falhou";
  return statusLabel(run.status);
}

function runStatusVariant(run: EvaluationRun): BadgeVariant {
  if (run.passed === true) return "ok";
  if (run.passed === false) return "err";
  return statusVariant(run.status);
}

function runTimestamp(run: EvaluationRun): string {
  return run.completed_at ?? run.started_at ?? run.created_at;
}

function sortRuns(runs: EvaluationRun[]): EvaluationRun[] {
  return [...runs].sort((a, b) => new Date(runTimestamp(b)).getTime() - new Date(runTimestamp(a)).getTime());
}

function sortTraces(traces: Trace[]): Trace[] {
  return [...traces].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
}

function Badge({ variant = "default", children }: { variant?: BadgeVariant; children: ReactNode }) {
  return (
    <span className={`evo-badge ${variant !== "default" ? `evo-badge--${variant}` : ""}`}>
      <span className="evo-badge__dot" />
      {children}
    </span>
  );
}

function StatusBadge({ status }: { status: string }) {
  return <Badge variant={statusVariant(status)}>{statusLabel(status)}</Badge>;
}

function Copyable({ value }: { value: string }) {
  return (
    <span className="evo-copyable">
      <span title={value}>{value}</span>
      <Copy size={11} />
    </span>
  );
}

function EmptyState({
  title,
  body,
  href,
  action,
}: {
  title: string;
  body: string;
  href?: string;
  action?: string;
}) {
  return (
    <div className="evo-overview-empty">
      <strong>{title}</strong>
      <span>{body}</span>
      {href && action ? (
        <Link href={href} className="evo-btn evo-btn--sm">
          {action} <ArrowRight size={12} />
        </Link>
      ) : null}
    </div>
  );
}

function PageHeader({
  projectName,
  projectSlug,
  orgName,
  orgSlug,
  environment,
  environmentLabel,
  loadedTraces,
  loadedRubrics,
  loadedRuns,
}: {
  projectName: string;
  projectSlug: string;
  orgName: string;
  orgSlug: string;
  environment?: string;
  environmentLabel: string;
  loadedTraces: number;
  loadedRubrics: number;
  loadedRuns: number;
}) {
  const refreshHref = environment
    ? `/o/${orgSlug}/p/${projectSlug}?environment=${encodeURIComponent(environment)}`
    : `/o/${orgSlug}/p/${projectSlug}`;
  return (
    <div className="evo-page-header">
      <div>
        <p className="evo-page-header__eyebrow">Workspace · {orgName}</p>
        <h1 className="evo-page-header__title">{projectName}</h1>
        <div className="evo-page-header__subtitle">
          Resumo de operacao · ambiente {environmentLabel} · {fmtInteger(loadedTraces)} traces / {fmtInteger(loadedRubrics)} rubricas / {fmtInteger(loadedRuns)} runs carregados.
        </div>
      </div>
      <div className="evo-page-header__actions">
        <button
          className="evo-btn evo-btn--sm"
          type="button"
          disabled
          data-status="planned"
          title="Filtro de janela - em breve"
        >
          <Clock size={13} /> Ultimos 7 dias
        </button>
        <Link href={refreshHref} className="evo-btn evo-btn--sm" title="Atualizar overview">
          <RefreshCw size={13} /> Atualizar
        </Link>
        <Link href={`/o/${orgSlug}/p/${projectSlug}/evaluations`} className="evo-btn evo-btn--sm evo-btn--primary">
          <Play size={13} /> Rodar avaliacao
        </Link>
      </div>
    </div>
  );
}

function OverviewAlertBanner({
  problemTraces,
  errorCount,
  partialCount,
  tracesHref,
}: {
  problemTraces: Trace[];
  errorCount: number;
  partialCount: number;
  tracesHref: (tab: string) => string;
}) {
  if (problemTraces.length === 0) return null;
  const tab = errorCount > 0 ? "errors" : "flagged";
  const variant: "error" | "warn" = errorCount > 0 ? "error" : "warn";
  const parts: string[] = [];
  if (errorCount > 0) parts.push(`${fmtInteger(errorCount)} com erro`);
  if (partialCount > 0) parts.push(`${fmtInteger(partialCount)} parciais`);
  const summary = parts.length > 0
    ? parts.join(" · ")
    : `${fmtInteger(problemTraces.length)} status diferente de ok`;
  return (
    <Link
      href={tracesHref(tab)}
      className={`evo-overview-alert evo-overview-alert--${variant}`}
      data-testid="overview-alert-banner"
    >
      <span className="evo-overview-alert__icon" aria-hidden="true">
        <AlertCircle size={15} />
      </span>
      <span className="evo-overview-alert__body">
        <strong>
          {fmtInteger(problemTraces.length)} trace(s) precisam de atencao na amostra carregada
        </strong>
        <span>{summary} · revise antes do proximo deploy.</span>
      </span>
      <span className="evo-overview-alert__cta evo-mono">
        Revisar traces <ArrowRight size={12} />
      </span>
    </Link>
  );
}

function OverviewMetricCard({
  label,
  value,
  hint,
  icon,
  variant = "default",
}: {
  label: string;
  value: string;
  hint: string;
  icon: ReactNode;
  variant?: BadgeVariant;
}) {
  return (
    <div className={`evo-overview-metric evo-overview-metric--${variant}`}>
      <div className="evo-overview-metric__label">
        {icon}
        {label}
      </div>
      <div className="evo-overview-metric__value">{value}</div>
      <div className="evo-overview-metric__hint">{hint}</div>
    </div>
  );
}

function ProjectStatusCard({
  kpis,
  recentTraces,
  recentFlagged,
  rubrics,
  runs,
}: {
  kpis: OverviewResponse["kpis"];
  recentTraces: Trace[];
  recentFlagged: Trace[];
  rubrics: Rubric[];
  runs: EvaluationRun[];
}) {
  const loadedProblemCount = recentTraces.filter((trace) => trace.status !== "ok").length;
  const flaggedCount = recentFlagged.length || loadedProblemCount;
  const overviewHasErrors = kpis.error_rate > 0;
  const title =
    kpis.traces === 0
      ? "Aguardando primeiro sinal"
      : flaggedCount > 0
      ? "Revisar traces carregados"
      : overviewHasErrors
      ? "Taxa de erro no overview"
      : rubrics.length === 0
      ? "Observabilidade sem rubricas"
      : runs.length === 0
      ? "Avaliacao pronta para iniciar"
      : "Operacao sem erro na amostra";
  const variant: BadgeVariant =
    kpis.traces === 0 ? "info" : flaggedCount > 0 || overviewHasErrors ? "warn" : runs.length === 0 ? "info" : "ok";
  const body =
    kpis.traces === 0
      ? "O overview ainda nao recebeu traces neste ambiente. Configure uma chave e envie a primeira execucao instrumentada."
      : flaggedCount > 0
      ? "A amostra carregada contem traces com status diferente de ok. Abra Traces para ver causa, duracao e metadata."
      : overviewHasErrors
      ? "O endpoint de overview retornou taxa de erro acima de zero, mas a amostra recente nao trouxe um trace problematico."
      : rubrics.length === 0
      ? "Traces existem, mas ainda nao ha rubricas cadastradas para avaliar qualidade."
      : runs.length === 0
      ? "Ha traces e rubricas disponiveis; o proximo passo real e rodar uma avaliacao."
      : "Nenhum erro apareceu nos traces recentes carregados, e ja existem runs de avaliacao no projeto.";

  return (
    <section className={`evo-overview-status evo-overview-status--${variant}`}>
      <div>
        <Badge variant={variant}>Status do projeto</Badge>
        <h2>{title}</h2>
        <p>{body}</p>
      </div>
      <dl className="evo-overview-status__facts">
        <div>
          <dt>Traces na janela</dt>
          <dd>{fmtInteger(kpis.traces)}</dd>
        </div>
        <div>
          <dt>Problemas carregados</dt>
          <dd>{fmtInteger(flaggedCount)}</dd>
        </div>
        <div>
          <dt>Rubricas</dt>
          <dd>{fmtInteger(rubrics.length)}</dd>
        </div>
        <div>
          <dt>Runs avaliacao</dt>
          <dd>{fmtInteger(runs.length)}</dd>
        </div>
      </dl>
    </section>
  );
}

function AreaChart({ data }: { data: ChartPoint[] }) {
  if (data.length === 0) {
    return (
      <EmptyState
        title="Sem serie diaria"
        body="O endpoint de overview nao retornou custo por dia para este ambiente."
      />
    );
  }

  const width = 560;
  const height = 200;
  const max = Math.max(...data.map((d) => d.cost), 1);
  const step = data.length > 1 ? width / (data.length - 1) : width;
  const points = data.map((d, i) => [i * step, height - 30 - (d.cost / max) * (height - 58)]);
  const line = points.map((p, i) => `${i === 0 ? "M" : "L"} ${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(" ");
  const area = `${line} L ${points[points.length - 1][0]} ${height - 30} L 0 ${height - 30} Z`;

  return (
    <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" className="evo-overview-chart" role="img" aria-label="Custo diario retornado pelo overview">
      <defs>
        <linearGradient id="evo-overview-area-grad" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.35" />
          <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
        </linearGradient>
      </defs>
      {[0.25, 0.5, 0.75].map((t) => (
        <line key={t} x1="0" x2={width} y1={28 + (height - 58) * t} y2={28 + (height - 58) * t} stroke="var(--border-subtle)" strokeDasharray="3 4" />
      ))}
      <path d={area} fill="url(#evo-overview-area-grad)" />
      <path d={line} fill="none" stroke="var(--accent)" strokeWidth="1.8" strokeLinejoin="round" />
      {points.map((p, i) => i % Math.ceil(points.length / 8) === 0 ? <circle key={i} cx={p[0]} cy={p[1]} r="2.5" fill="var(--accent)" /> : null)}
      {data.map((d, i) => i % Math.ceil(data.length / 8) === 0 ? (
        <text key={d.label + i} x={i * step} y={height - 8} textAnchor="middle" fontSize="10" fill="var(--text-faint)" fontFamily="var(--font-evo-mono)">{d.label}</text>
      ) : null)}
    </svg>
  );
}

function ModelTable({ breakdown }: { breakdown: OverviewResponse["model_breakdown"] }) {
  const totalCalls = breakdown.reduce((sum, item) => sum + item.calls, 0) || 1;
  return (
    <table className="evo-table">
      <thead>
        <tr><th>Modelo</th><th>Calls</th><th>Custo</th><th>Share</th></tr>
      </thead>
      <tbody>
        {breakdown.length === 0 ? (
          <tr><td colSpan={4} className="evo-empty-row">Nenhuma chamada LLM registrada no overview.</td></tr>
        ) : breakdown.map((model) => {
          const share = (model.calls / totalCalls) * 100;
          return (
            <tr key={`${model.provider}-${model.model}`}>
              <td>
                <div className="evo-model-cell">
                  <span className="evo-table__name">{model.model ?? "modelo desconhecido"}</span>
                  <span>{model.provider ?? "provider desconhecido"}</span>
                </div>
              </td>
              <td className="evo-table__num">{fmtInteger(model.calls)}</td>
              <td className="evo-table__num">{formatCost(model.cost_usd)}</td>
              <td>
                <div className="evo-share">
                  <span><i style={{ width: `${Math.min(100, share).toFixed(1)}%` }} /></span>
                  <b>{share.toFixed(0)}%</b>
                </div>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function RecentTracesCard({ traces, org, project }: { traces: Trace[]; org: string; project: string }) {
  return (
    <section className="evo-overview-card">
      <div className="evo-card__header">
        <div>
          <h3 className="evo-card__title">Traces recentes</h3>
          <div className="evo-card__subtitle">Amostra real carregada de /traces</div>
        </div>
        <Link className="evo-btn evo-btn--sm" href={`/o/${org}/p/${project}/traces`}>
          Ver traces <ArrowRight size={12} />
        </Link>
      </div>
      <div className="evo-overview-list">
        {traces.length === 0 ? (
          <EmptyState
            title="Nenhum trace recente"
            body="Quando o SDK enviar traces, eles aparecem aqui com status, modelo, custo e duracao."
            href={`/o/${org}/p/${project}/keys`}
            action="Configurar chave"
          />
        ) : traces.slice(0, 5).map((trace) => {
          const model = getTraceModelLabel(trace);
          const cause = getTraceCauseLabel(trace);
          return (
            <Link className="evo-overview-row" href={`/o/${org}/p/${project}/traces/${trace.id}`} key={trace.id}>
              <StatusBadge status={trace.status} />
              <span className="evo-overview-row__main">
                <strong>{trace.name}</strong>
                <small>
                  {trace.service ?? "servico nao informado"} · {model ?? "modelo nao informado"}
                  {cause ? ` · causa: ${cause}` : ""}
                </small>
              </span>
              <span className="evo-overview-row__meta">
                {formatLatency(trace.duration_ms)} · {formatCost(trace.total_cost_usd)} · {timeAgo(trace.created_at)}
              </span>
            </Link>
          );
        })}
      </div>
    </section>
  );
}

function EvaluationSnapshotCard({
  runs,
  rubrics,
  org,
  project,
}: {
  runs: EvaluationRun[];
  rubrics: Rubric[];
  org: string;
  project: string;
}) {
  const rubricMap = new Map(rubrics.map((rubric) => [rubric.id, rubric]));
  const latestRuns = sortRuns(runs).slice(0, 5);
  const scores = runs.map((run) => run.aggregate_score).filter((score): score is number => score !== null);
  const avgScore = scores.length ? scores.reduce((sum, score) => sum + score, 0) / scores.length : null;

  return (
    <section className="evo-overview-card">
      <div className="evo-card__header">
        <div>
          <h3 className="evo-card__title">Avaliacoes</h3>
          <div className="evo-card__subtitle">
            {runs.length > 0
              ? `${fmtInteger(runs.length)} run(s) carregadas · score medio ${fmtScore(avgScore)}`
              : "Status real das runs e rubricas do projeto"}
          </div>
        </div>
        <Link className="evo-btn evo-btn--sm" href={`/o/${org}/p/${project}/evaluations`}>
          Abrir avaliacoes <ArrowRight size={12} />
        </Link>
      </div>
      <div className="evo-overview-list">
        {latestRuns.length === 0 ? (
          <EmptyState
            title={rubrics.length === 0 ? "Nenhuma rubrica cadastrada" : "Nenhuma run de avaliacao"}
            body={
              rubrics.length === 0
                ? "Crie uma rubrica antes de rodar avaliacoes sobre traces."
                : "As rubricas existem; rode uma avaliacao quando houver trace elegivel."
            }
            href={rubrics.length === 0 ? `/o/${org}/p/${project}/rubrics` : `/o/${org}/p/${project}/evaluations`}
            action={rubrics.length === 0 ? "Criar rubrica" : "Rodar avaliacao"}
          />
        ) : latestRuns.map((run) => {
          const rubric = rubricMap.get(run.rubric_id);
          return (
            <Link className="evo-overview-row" href={`/o/${org}/p/${project}/traces/${run.trace_id}`} key={run.id}>
              <Badge variant={runStatusVariant(run)}>{runStatusLabel(run)}</Badge>
              <span className="evo-overview-row__main">
                <strong>{rubric ? rubric.slug : run.rubric_id.slice(0, 12)}</strong>
                <small>trace {run.trace_id.slice(0, 12)} · v{run.rubric_version}</small>
              </span>
              <span className="evo-overview-row__meta">
                {fmtScore(run.aggregate_score)} · {formatCost(run.cost_usd)} · {timeAgo(runTimestamp(run))}
              </span>
            </Link>
          );
        })}
      </div>
    </section>
  );
}

function OperationalSignals({
  kpis,
  traces,
  rubrics,
  runs,
  org,
  project,
  environment,
  environmentLabel,
}: {
  kpis: OverviewResponse["kpis"];
  traces: Trace[];
  rubrics: Rubric[];
  runs: EvaluationRun[];
  org: string;
  project: string;
  environment?: string;
  environmentLabel: string;
}) {
  const errorCount = traces.filter((trace) => trace.status === "error").length;
  const partialCount = traces.filter((trace) => trace.status === "partial").length;
  const signals: Array<{ title: string; body: string; href: string; variant: BadgeVariant }> = [];

  if (kpis.traces === 0) {
    signals.push({
      title: "Sem traces neste ambiente",
      body: `O cockpit ainda nao tem execucoes para resumir em ${environmentLabel}.`,
      href: `/o/${org}/p/${project}/keys`,
      variant: "info",
    });
  }
  const tracesHref = (tab: string) => {
    const params = new URLSearchParams({ tab });
    if (environment) params.set("environment", environment);
    return `/o/${org}/p/${project}/traces?${params.toString()}`;
  };
  if (errorCount > 0) {
    signals.push({
      title: `${fmtInteger(errorCount)} trace(s) recentes com erro`,
      body: "Abrir a lista filtrada ajuda a ver causa, metadata e waterfall.",
      href: tracesHref("errors"),
      variant: "err",
    });
  } else if (kpis.error_rate > 0) {
    signals.push({
      title: `Taxa de erro ${formatPercent(kpis.error_rate)}`,
      body: "O overview retornou erro na janela, mas a amostra recente nao trouxe a linha exata.",
      href: tracesHref("errors"),
      variant: "warn",
    });
  }
  if (partialCount > 0) {
    signals.push({
      title: `${fmtInteger(partialCount)} trace(s) parciais carregados`,
      body: "Status parcial vem do payload do trace; revise antes de comparar resultados.",
      href: tracesHref("flagged"),
      variant: "warn",
    });
  }
  if (rubrics.length === 0) {
    signals.push({
      title: "Sem rubricas",
      body: "Avaliacoes precisam de uma rubrica versionada.",
      href: `/o/${org}/p/${project}/rubrics`,
      variant: "info",
    });
  }
  if (rubrics.length > 0 && runs.length === 0) {
    signals.push({
      title: "Rubricas sem runs",
      body: "Ha rubricas cadastradas, mas nenhuma avaliacao foi rodada ainda.",
      href: `/o/${org}/p/${project}/evaluations`,
      variant: "eval",
    });
  }

  return (
    <section className="evo-overview-card">
      <div className="evo-card__header">
        <div>
          <h3 className="evo-card__title">Sinais operacionais</h3>
          <div className="evo-card__subtitle">Somente condicoes derivadas dos payloads carregados</div>
        </div>
      </div>
      <div className="evo-overview-signal-list">
        {signals.length === 0 ? (
          <div className="evo-overview-signal evo-overview-signal--ok">
            <CheckCircle2 size={15} />
            <span>
              <strong>Sem sinal critico na amostra</strong>
              <small>Nenhum erro ou lacuna basica apareceu nos dados carregados para esta Overview.</small>
            </span>
          </div>
        ) : signals.map((signal) => (
          <Link className={`evo-overview-signal evo-overview-signal--${signal.variant}`} href={signal.href} key={signal.title}>
            <AlertCircle size={15} />
            <span>
              <strong>{signal.title}</strong>
              <small>{signal.body}</small>
            </span>
            <ArrowRight size={13} />
          </Link>
        ))}
      </div>
    </section>
  );
}

function NextActions({
  hasTraces,
  hasRubrics,
  hasRuns,
  org,
  project,
}: {
  hasTraces: boolean;
  hasRubrics: boolean;
  hasRuns: boolean;
  org: string;
  project: string;
}) {
  const actions: Array<{ icon: ReactNode; title: string; body: string; href: string; tone?: "primary" }> = [
    hasTraces
      ? {
          icon: <Activity size={16} />,
          title: "Abrir traces",
          body: "Ver execucoes recentes, waterfall, metadata e feedback humano.",
          href: `/o/${org}/p/${project}/traces`,
          tone: "primary",
        }
      : {
          icon: <KeyRound size={16} />,
          title: "Configurar chave",
          body: "Criar uma chave API para conectar o SDK e enviar o primeiro trace.",
          href: `/o/${org}/p/${project}/keys`,
          tone: "primary",
        },
    hasRubrics
      ? {
          icon: <Target size={16} />,
          title: hasRuns ? "Revisar avaliacoes" : "Rodar avaliacao",
          body: hasRuns ? "Abrir runs, scores e rubricas usadas." : "Executar uma rubrica existente sobre um trace.",
          href: `/o/${org}/p/${project}/evaluations`,
        }
      : {
          icon: <ListChecks size={16} />,
          title: "Criar rubrica",
          body: "Definir criterios versionados antes de medir qualidade.",
          href: `/o/${org}/p/${project}/rubrics`,
        },
    {
      icon: <Database size={16} />,
      title: "Organizar datasets",
      body: "Abrir datasets reais do projeto para curadoria e reuso.",
      href: `/o/${org}/p/${project}/datasets`,
    },
    {
      icon: <Sparkles size={16} />,
      title: "Gerenciar prompts",
      body: "Ver templates e versoes de prompt cadastrados.",
      href: `/o/${org}/p/${project}/prompts`,
    },
  ];

  return (
    <section className="evo-overview-actions" aria-label="Proximos passos">
      {actions.map((action) => (
        <Link
          className={`evo-overview-action ${action.tone === "primary" ? "evo-overview-action--primary" : ""}`}
          href={action.href}
          key={action.title}
        >
          <span className="evo-overview-action__icon">{action.icon}</span>
          <span>
            <strong>{action.title}</strong>
            <small>{action.body}</small>
          </span>
          <ArrowRight size={13} />
        </Link>
      ))}
    </section>
  );
}

function ProjectContext({
  resolved,
  environmentLabel,
}: {
  resolved: Awaited<ReturnType<typeof resolveProject>>;
  environmentLabel: string;
}) {
  return (
    <section className="evo-overview-context" aria-label="Contexto do projeto">
      <div>
        <span>Projeto</span>
        <strong>{resolved.project_name}</strong>
        <Copyable value={resolved.project_id} />
      </div>
      <div>
        <span>Workspace</span>
        <strong>{resolved.org_name}</strong>
        <small>{resolved.org_slug}</small>
      </div>
      <div>
        <span>Ambiente</span>
        <strong>{environmentLabel}</strong>
        <small>
          {environmentLabel === "sem filtro"
            ? "Sem filtro de ambiente em overview/traces"
            : "Filtro aplicado em overview/traces; rubricas e runs sao do projeto"}
        </small>
      </div>
    </section>
  );
}

function NoToken() {
  return <AuthRequiredPanel layout="main" />;
}

export default async function ProjectOverviewPage({ params, searchParams }: Props) {
  const { org, project } = await params;
  const qp = await searchParams;
  const environment = qp.environment;
  const environmentLabel = environment ?? "sem filtro";

  if (!(await hasAuthToken())) return <NoToken />;

  const resolved = await resolveProject(org, project);
  const projectId = resolved.project_id;
  const [overview, recentRes, evalsRes, rubricsRes] = await Promise.all([
    getOverview(projectId, environment),
    getTraces({ projectId, limit: 8, environment }),
    getProjectEvaluations(projectId, 25),
    getRubrics(projectId),
  ]);

  const { kpis, cost_by_day, model_breakdown, recent_flagged } = overview;
  const recentTraces = sortTraces(recentRes.data);
  const recentRuns = sortRuns(evalsRes.data);
  const rubrics = rubricsRes.data;
  const problemTraces = (recent_flagged.length ? recent_flagged : recentTraces.filter((trace) => trace.status !== "ok")).slice(0, 6);
  const costSeries = cost_by_day.slice(-14).map((d) => ({ label: fmtShortDate(d.day), cost: d.cost_usd, traces: d.traces }));
  const totalDailyTraces = cost_by_day.reduce((sum, day) => sum + day.traces, 0);

  const errorCount = recentTraces.filter((trace) => trace.status === "error").length;
  const partialCount = recentTraces.filter((trace) => trace.status === "partial").length;
  const tracesHrefFor = (tab: string) => {
    const params = new URLSearchParams({ tab });
    if (environment) params.set("environment", environment);
    return `/o/${org}/p/${project}/traces?${params.toString()}`;
  };

  return (
    <div className="evo-page evo-overview-page">
      <PageHeader
        projectName={resolved.project_name}
        projectSlug={resolved.project_slug}
        orgName={resolved.org_name}
        orgSlug={resolved.org_slug}
        environment={environment}
        environmentLabel={environmentLabel}
        loadedTraces={recentTraces.length}
        loadedRubrics={rubrics.length}
        loadedRuns={recentRuns.length}
      />

      <OverviewAlertBanner
        problemTraces={problemTraces}
        errorCount={errorCount}
        partialCount={partialCount}
        tracesHref={tracesHrefFor}
      />

      <div className="evo-overview-hero">
        <div className="evo-overview-hero__panel">
          <Badge variant="info">Cockpit operacional</Badge>
          <h2 className="evo-overview-hero__title">Visao geral honesta do projeto</h2>
          <p>
            Traces, custo, modelos, rubricas e runs de avaliacao aparecem aqui somente quando os endpoints atuais retornam dados.
            Lacunas viram orientacao acionavel para os modulos reais.
          </p>
          <ProjectContext resolved={resolved} environmentLabel={environmentLabel} />
        </div>
        <ProjectStatusCard
          kpis={kpis}
          recentTraces={recentTraces}
          recentFlagged={recent_flagged}
          rubrics={rubrics}
          runs={recentRuns}
        />
      </div>

      <section className="evo-overview-metric-grid" aria-label="Resumo operacional">
        <OverviewMetricCard label="Traces" icon={<Activity size={13} />} value={fmtNumber(kpis.traces)} hint="Fonte: analytics/overview" variant="info" />
        <OverviewMetricCard label="p95 latencia" icon={<Clock size={13} />} value={formatLatency(kpis.latency_p95_ms)} hint="Fonte: analytics/overview" variant="warn" />
        <OverviewMetricCard label="Custo" icon={<Coins size={13} />} value={formatCost(kpis.cost_usd)} hint="USD retornado pelo overview" variant="eval" />
        <OverviewMetricCard label="Erro" icon={<AlertCircle size={13} />} value={formatPercent(kpis.error_rate)} hint="Taxa retornada pelo overview" variant={kpis.error_rate > 0 ? "err" : "ok"} />
        <OverviewMetricCard label="Score medio" icon={<Target size={13} />} value={fmtScore(kpis.avg_score)} hint={kpis.avg_score === null ? "Sem fonte de score no payload" : "Fonte: analytics/overview"} variant="eval" />
      </section>

      <NextActions
        hasTraces={kpis.traces > 0 || recentTraces.length > 0}
        hasRubrics={rubrics.length > 0}
        hasRuns={recentRuns.length > 0}
        org={org}
        project={project}
      />

      <section className="evo-overview-main-grid">
        <RecentTracesCard traces={recentTraces} org={org} project={project} />
        <EvaluationSnapshotCard runs={recentRuns} rubrics={rubrics} org={org} project={project} />
      </section>

      <section className="evo-overview-main-grid evo-overview-main-grid--wide-left">
        <div className="evo-overview-card">
          <div className="evo-card__header">
            <div>
              <h3 className="evo-card__title">Custo diario</h3>
              <div className="evo-card__subtitle">
                {cost_by_day.length > 0
                  ? `${fmtInteger(totalDailyTraces)} trace(s) na serie carregada`
                  : "Sem serie de custo retornada"}
              </div>
            </div>
            <div className="evo-row">
              <Badge variant="info">analytics</Badge>
              <Link
                className="evo-btn evo-btn--ghost evo-btn--sm evo-btn--icon"
                href={`/o/${org}/p/${project}/exports`}
                aria-label="Abrir exports"
                title="Abrir exports"
              >
                <Download size={13} />
              </Link>
            </div>
          </div>
          <div className="evo-card__body">
            <AreaChart data={costSeries} />
          </div>
        </div>

        <div className="evo-overview-card">
          <div className="evo-card__header">
            <div>
              <h3 className="evo-card__title">Custo por modelo</h3>
              <div className="evo-card__subtitle">Provider, modelo, calls e custo vindos do overview</div>
            </div>
            <Link className="evo-btn evo-btn--ghost evo-btn--sm" href={`/o/${org}/p/${project}/traces`}>
              Ver detalhes <ArrowRight size={12} />
            </Link>
          </div>
          <div className="evo-card__body evo-card__body--flush">
            <ModelTable breakdown={model_breakdown} />
          </div>
        </div>
      </section>

      <section className="evo-overview-main-grid">
        <OperationalSignals
          kpis={kpis}
          traces={problemTraces}
          rubrics={rubrics}
          runs={recentRuns}
          org={org}
          project={project}
          environment={environment}
          environmentLabel={environmentLabel}
        />
        <div className="evo-overview-card">
          <div className="evo-card__header">
            <div>
              <h3 className="evo-card__title">Atalhos reais</h3>
              <div className="evo-card__subtitle">Rotas existentes do AppShell</div>
            </div>
          </div>
          <div className="evo-overview-shortcuts">
            <Link href={`/o/${org}/p/${project}/traces`}><Activity size={14} /> Traces</Link>
            <Link href={`/o/${org}/p/${project}/evaluations`}><BarChart3 size={14} /> Avaliacoes</Link>
            <Link href={`/o/${org}/p/${project}/rubrics`}><ListChecks size={14} /> Rubricas</Link>
            <Link href={`/o/${org}/p/${project}/datasets`}><Database size={14} /> Datasets</Link>
            <Link href={`/o/${org}/p/${project}/prompts`}><FileText size={14} /> Prompts</Link>
            <Link href={`/o/${org}/p/${project}/keys`}><KeyRound size={14} /> Chaves API</Link>
          </div>
        </div>
      </section>

      <footer className="evo-footer">
        <span>EvalOps Studio</span>
        <span className="evo-spacer" />
        <a href="/docs">Documentacao</a>
        <a href={`${apiRoot()}/health/readiness`} target="_blank" rel="noreferrer">Readiness API</a>
      </footer>
    </div>
  );
}
