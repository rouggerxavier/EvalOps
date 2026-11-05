import Link from "next/link";
import {
  Activity,
  AlertCircle,
  ArrowRight,
  Check,
  Clock,
  Coins,
  RefreshCw,
  Target,
} from "lucide-react";

import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import {
  AreaChart,
  AttentionStrip,
  Badge,
  Card,
  Copyable,
  Metric,
  PageHeader,
  StatusBadge,
} from "@/components/ui/index";
import {
  getAttention,
  getCoverage,
  getOverview,
  getRubrics,
  getSdkStatus,
  getTraces,
  hasAuthToken,
  resolveProject,
} from "@/lib/api";
import { getActiveEnvironment } from "@/lib/active-env";
import { formatCost, formatLatency, formatPercent } from "@/lib/format";
import { getTraceCauseLabel, getTraceModelLabel } from "@/lib/trace-display";
import type { Trace } from "@/lib/types";

import {
  EvaluateHeaderButton,
  OverviewSuggestions,
  WindowSelect,
} from "./overview-actions";

type Window = "24h" | "7d" | "30d";

type Props = {
  params: Promise<{ org: string; project: string }>;
  searchParams: Promise<{ environment?: string; window?: string }>;
};

function fmtInteger(n: number): string {
  return new Intl.NumberFormat("pt-BR").format(n);
}

function fmtCompact(n: number): string {
  return new Intl.NumberFormat("pt-BR", {
    notation: n >= 10000 ? "compact" : "standard",
    maximumFractionDigits: 1,
  }).format(n);
}

function fmtShortDate(value: string): string {
  return new Date(value).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", timeZone: "UTC" });
}

function fmtScore(value: number | null): string {
  return value === null ? "—" : value.toFixed(2);
}

function timeAgo(value: string): string {
  const delta = Date.now() - new Date(value).getTime();
  const minutes = Math.max(0, Math.round(delta / 60000));
  if (minutes < 1) return "agora";
  if (minutes < 60) return `${minutes}min`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h`;
  const days = Math.round(hours / 24);
  return `${days}d`;
}

function windowLabel(window: Window): string {
  if (window === "24h") return "24 horas";
  if (window === "30d") return "30 dias";
  return "7 dias";
}

function parseWindow(value: string | undefined): Window {
  if (value === "24h" || value === "30d") return value;
  return "7d";
}

function isRagTrace(trace: Trace): boolean {
  return trace.name?.startsWith("rag.") ?? false;
}

const CAUSE_LABELS: Record<string, string> = {
  schema_mismatch: "schema mismatch",
  timeout: "timeout",
  partial_trace: "trace parcial",
  trace_error: "erro",
};

export default async function ProjectOverviewPage({ params, searchParams }: Props) {
  const { org, project } = await params;
  const qp = await searchParams;
  const environment = await getActiveEnvironment(qp.environment);
  const window_ = parseWindow(qp.window);

  if (!(await hasAuthToken())) return <AuthRequiredPanel layout="main" />;

  const resolved = await resolveProject(org, project);
  const projectId = resolved.project_id;

  const [overview, attention, coverage, sdk, rubricsRes, flaggedRes] = await Promise.all([
    getOverview(projectId, environment, window_),
    getAttention(projectId).catch(() => ({ count: 0, items: [] as const })),
    getCoverage(projectId, window_).catch(() => ({ data: [] as const })),
    getSdkStatus(projectId).catch(() => null),
    getRubrics(projectId).catch(() => ({ data: [] })),
    getTraces({ projectId, limit: 4, status: "error,partial", environment }).catch(() => ({ data: [] as Trace[], next_cursor: null })),
  ]);

  const { kpis, cost_by_day, model_breakdown, recent_flagged } = overview;
  const totalCalls = model_breakdown.reduce((sum, m) => sum + m.calls, 0) || 1;
  const flaggedTraces = (flaggedRes.data.length > 0 ? flaggedRes.data : recent_flagged).slice(0, 4);

  const costSeries = cost_by_day.slice(-14).map((d) => ({ label: fmtShortDate(d.day), value: d.cost_usd }));
  const traceSpark = cost_by_day.slice(-14).map((d) => d.traces);
  const costSpark = cost_by_day.slice(-14).map((d) => d.cost_usd);

  const tracesHref = `/o/${org}/p/${project}/traces${environment ? `?environment=${encodeURIComponent(environment)}` : ""}`;
  const refreshHref = `/o/${org}/p/${project}?window=${window_}${environment ? `&environment=${encodeURIComponent(environment)}` : ""}`;

  const rubrics = rubricsRes.data.map((r) => ({ id: r.id, slug: r.slug, current_version: r.current_version }));
  const candidateTraces = flaggedTraces.map((t) => ({ id: t.id, name: t.name }));
  const actionsCtx = { org, project, projectId, environment, rubrics, candidateTraces };

  return (
    <div className="page">
      <PageHeader
        eyebrow={`Workspace · ${resolved.org_name}`}
        title={resolved.project_name}
        subtitle={`Resumo de operação · janela: últimos ${windowLabel(window_)} · env: ${environment ?? "todos"}`}
        actions={
          <>
            <WindowSelect org={org} project={project} current={window_} environment={environment} />
            <Link href={refreshHref} className="btn btn--sm" title="Atualizar overview">
              <RefreshCw size={12} /> Atualizar
            </Link>
            <EvaluateHeaderButton ctx={actionsCtx} />
          </>
        }
      />

      {attention.count > 0 ? (
        <AttentionStrip
          title={`${fmtInteger(attention.count)} traces precisam de atenção nas últimas 24h`}
          description="Schema mismatch, timeouts e baixa confiança em respostas RAG. Concentre-se nesta lista antes do próximo deploy."
          action={
            <Link href={tracesHref} className="btn btn--sm">
              Revisar traces <ArrowRight size={11} />
            </Link>
          }
        />
      ) : null}

      <section className="kpi-grid kpi-grid--5">
        <Metric
          label="Traces"
          icon={<Activity size={12} />}
          value={fmtCompact(kpis.traces)}
          spark={traceSpark.length > 1 ? traceSpark : undefined}
        />
        <Metric
          label="p95 latência"
          icon={<Clock size={12} />}
          value={(kpis.latency_p95_ms / 1000).toFixed(2)}
          unit="s"
          sparkColor="var(--warning)"
        />
        <Metric
          label="Custo"
          icon={<Coins size={12} />}
          value={formatCost(kpis.cost_usd)}
          spark={costSpark.length > 1 ? costSpark : undefined}
          sparkColor="var(--info)"
        />
        <Metric
          label="Taxa de erro"
          icon={<AlertCircle size={12} />}
          value={formatPercent(kpis.error_rate)}
          sparkColor="var(--danger)"
        />
        <Metric
          label="Score médio"
          icon={<Target size={12} />}
          value={fmtScore(kpis.avg_score)}
          sparkColor="var(--success)"
        />
      </section>

      <section className="grid-2" style={{ marginBottom: 12 }}>
        <Card
          title="Custo & volume por dia"
          subtitle="USD · últimos 14 dias"
          action={<Badge variant="info">cost</Badge>}
        >
          <AreaChart data={costSeries} color="var(--info)" />
        </Card>

        <Card
          title="Custo por modelo"
          action={
            <Link href={tracesHref} className="btn btn--ghost btn--sm">
              Ver detalhes <ArrowRight size={11} />
            </Link>
          }
          flush
        >
          <table className="t">
            <thead>
              <tr>
                <th>Modelo</th>
                <th className="t__num">Calls</th>
                <th className="t__num">Custo</th>
                <th>Share</th>
              </tr>
            </thead>
            <tbody>
              {model_breakdown.length === 0 ? (
                <tr><td colSpan={4} className="t__empty">Sem chamadas LLM na janela.</td></tr>
              ) : model_breakdown.map((m) => {
                const share = m.calls / totalCalls;
                return (
                  <tr key={`${m.provider}-${m.model}`}>
                    <td>
                      <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
                        <span className="t__name">{m.model ?? "—"}</span>
                        <span className="t__faint mono" style={{ fontSize: 10 }}>{m.provider ?? "—"}</span>
                      </div>
                    </td>
                    <td className="t__num t__muted">{fmtInteger(m.calls)}</td>
                    <td className="t__num">{formatCost(m.cost_usd)}</td>
                    <td>
                      <span className="share">
                        <span className="share__bar"><i style={{ width: `${(share * 100).toFixed(0)}%` }} /></span>
                        <span className="share__pct">{Math.round(share * 100)}%</span>
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>
      </section>

      <Card
        title="Últimos traces com problema"
        subtitle="status diferente de ok · ordenado por mais recente"
        action={
          <Link href={tracesHref} className="btn btn--sm">
            Ver todos os traces <ArrowRight size={11} />
          </Link>
        }
        flush
      >
        <table className="t">
          <thead>
            <tr>
              <th>Trace</th>
              <th>ID</th>
              <th>Status</th>
              <th>Causa</th>
              <th className="t__num">Duração</th>
              <th className="t__num">Custo</th>
              <th>Modelo</th>
              <th>Quando</th>
              <th style={{ width: 32 }}></th>
            </tr>
          </thead>
          <tbody>
            {flaggedTraces.length === 0 ? (
              <tr><td colSpan={9} className="t__empty">Nenhum trace com problema nesta janela 🎉</td></tr>
            ) : flaggedTraces.map((t) => {
              const cause = getTraceCauseLabel(t);
              const model = getTraceModelLabel(t);
              return (
                <tr key={t.id} className="is-flagged">
                  <td>
                    <Link href={`/o/${org}/p/${project}/traces/${t.id}`} style={{ display: "flex", flexDirection: "column", gap: 1, color: "inherit", textDecoration: "none" }}>
                      <span className="t__name">{t.name}</span>
                      <span className="t__faint mono" style={{ fontSize: 10 }}>
                        {t.service ?? "—"}{isRagTrace(t) ? " · RAG" : ""}
                      </span>
                    </Link>
                  </td>
                  <td><Copyable value={t.id} display={t.id.slice(0, 12)} /></td>
                  <td><StatusBadge status={t.status} /></td>
                  <td>
                    {cause ? (
                      <span className="tag" style={{ color: "var(--danger)" }}>{CAUSE_LABELS[cause] ?? cause}</span>
                    ) : <span style={{ color: "var(--fg-4)" }}>—</span>}
                  </td>
                  <td className="t__num t__muted">{formatLatency(t.duration_ms)}</td>
                  <td className="t__num">{formatCost(t.total_cost_usd)}</td>
                  <td className="t__mono">{model ?? "—"}</td>
                  <td className="t__faint" style={{ fontSize: 11 }}>{timeAgo(t.created_at)}</td>
                  <td><ArrowRight size={12} className="t__chev" /></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Card>

      <div style={{ height: 12 }} />

      <section className="grid-3">
        <Card title="Saúde do SDK" subtitle="ingestão · últimos 60min">
          <SdkHealth sdk={sdk} />
        </Card>

        <Card title="Próximos passos sugeridos">
          <OverviewSuggestions ctx={actionsCtx} />
        </Card>

        <Card title="Cobertura por avaliação" subtitle="% de traces com pelo menos uma run">
          <CoverageList items={coverage.data} />
        </Card>
      </section>

      <footer className="app-footer">
        <span>© 2026 EvalOps Studio</span>
        <span className="spacer" />
        <Link href="/docs">Documentação</Link>
        <Link href="/health">Status</Link>
        <span className="row" style={{ gap: 5, color: "var(--success)" }}>
          <Check size={11} /> Sistemas operando
        </span>
      </footer>
    </div>
  );
}

function SdkHealth({ sdk }: { sdk: Awaited<ReturnType<typeof getSdkStatus>> | null }) {
  if (!sdk) {
    return <div style={{ fontSize: 12, color: "var(--fg-3)" }}>Sem sinal de ingestão na última hora.</div>;
  }
  const services = sdk.services_seen.slice(0, 2);
  return (
    <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
      <div style={{ flex: 1 }}>
        <div className="row" style={{ marginBottom: 8 }}>
          <Badge variant="ok">ingestão ok</Badge>
          <span className="mono" style={{ fontSize: 10, color: "var(--fg-3)" }}>
            p95 {formatLatency(sdk.p95_ingestion_ms)}
          </span>
        </div>
        <div style={{ fontSize: 12, color: "var(--fg-3)" }}>
          {services.length > 0 ? (
            <>Recebendo eventos de {services.map((s, i) => (
              <span key={s} className="mono">{i > 0 ? " e " : ""}{s}</span>
            ))}.</>
          ) : "Aguardando primeiro serviço instrumentado."}
        </div>
      </div>
      <div style={{ textAlign: "right" }}>
        <div className="mono" style={{ fontSize: 18, color: "var(--fg-1)" }}>
          {fmtInteger(Math.round(sdk.spans_per_minute))}
        </div>
        <div className="mono" style={{ fontSize: 10, color: "var(--fg-4)" }}>spans/min</div>
      </div>
    </div>
  );
}

function CoverageList({ items }: { items: ReadonlyArray<{ rubric_slug: string; coverage: number; runs_7d: number }> }) {
  if (items.length === 0) {
    return <div style={{ fontSize: 12, color: "var(--fg-3)" }}>Sem rubricas cadastradas neste projeto.</div>;
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {items.slice(0, 4).map((ev) => {
        const pct = Math.max(0, Math.min(1, ev.coverage));
        const color = pct >= 0.7 ? "var(--success)" : pct >= 0.4 ? "var(--warning)" : "var(--danger)";
        return (
          <div key={ev.rubric_slug} style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <div className="row" style={{ justifyContent: "space-between" }}>
              <span className="mono" style={{ fontSize: 12, color: "var(--fg-1)" }}>{ev.rubric_slug}</span>
              <span className="mono" style={{ fontSize: 11, color: "var(--fg-4)" }}>{Math.round(pct * 100)}%</span>
            </div>
            <div className="share__bar" style={{ width: "100%" }}>
              <i style={{ width: `${(pct * 100).toFixed(0)}%`, background: color }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

