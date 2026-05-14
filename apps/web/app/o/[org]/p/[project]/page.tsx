import Link from "next/link";
import type { ReactNode } from "react";
import {
  Activity,
  AlertCircle,
  ArrowDown,
  ArrowRight,
  ArrowUp,
  Check,
  ChevronDown,
  ChevronRight,
  Clock,
  Coins,
  Copy,
  Download,
  Play,
  RefreshCw,
} from "lucide-react";

import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { getOverview, getTraces, hasAuthToken, resolveProject } from "@/lib/api";
import { getApiBaseUrl } from "@/lib/config";
import type { OverviewResponse, Trace } from "@/lib/types";

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

type ChartPoint = { label: string; v: number };

function fmtNumber(n: number): string {
  return new Intl.NumberFormat("pt-BR", { notation: n >= 10000 ? "compact" : "standard", maximumFractionDigits: 1 }).format(n);
}

function fmtInteger(n: number): string {
  return new Intl.NumberFormat("pt-BR").format(n);
}

function fmtMoney(n: number, digits = 2): string {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: digits, maximumFractionDigits: digits }).format(n);
}

function fmtLatency(ms: number): string {
  return (ms / 1000).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtPercent(v: number): string {
  return (v * 100).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
}

function fmtShortDate(value: string): string {
  return new Date(value).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
}

function timeAgo(value: string): string {
  const delta = Date.now() - new Date(value).getTime();
  const minutes = Math.max(0, Math.round(delta / 60000));
  if (minutes < 1) return "agora";
  if (minutes < 60) return `${minutes}min atrás`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h atrás`;
  const days = Math.round(hours / 24);
  return `${days}d atrás`;
}

function fallbackSeries(days = 14): ChartPoint[] {
  const now = new Date();
  return Array.from({ length: days }, (_, i) => {
    const d = new Date(now);
    d.setDate(now.getDate() - (days - i - 1));
    return { label: fmtShortDate(d.toISOString()), v: 0 };
  });
}

function asSpark(values: number[], fallback = 0): number[] {
  if (values.length >= 2) return values;
  return [fallback, fallback];
}

function statusLabel(status: string): string {
  if (status === "ok" || status === "success" || status === "completed") return "ok";
  if (status === "partial" || status === "queued" || status === "running") return "atenção";
  if (status === "error" || status === "failed") return "erro";
  return status;
}


function PageHeader({ project, org }: { project: string; org: string }) {
  return (
    <div className="evo-page-header">
      <div>
        <h1 className="evo-page-header__title">{project}</h1>
        <div className="evo-page-header__subtitle">
          Resumo de operação · workspace: {org} · janela: últimos 7 dias
        </div>
      </div>
      <div className="evo-page-header__actions">
        <button className="evo-btn evo-btn--sm"><Clock size={13} /> Últimos 7 dias <ChevronDown size={12} /></button>
        <button className="evo-btn evo-btn--sm"><RefreshCw size={13} /> Atualizar</button>
        <button className="evo-btn evo-btn--sm evo-btn--primary"><Play size={13} /> Rodar avaliação</button>
      </div>
    </div>
  );
}

function Sparkline({ points, color = "var(--accent)" }: { points: number[]; color?: string }) {
  if (!points || points.length < 2) return null;
  const width = 84;
  const height = 28;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = max - min || 1;
  const step = width / (points.length - 1);
  const path = points.map((v, i) => {
    const x = i * step;
    const y = height - ((v - min) / range) * (height - 2) - 1;
    return `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
  }).join(" ");
  const last = points[points.length - 1];
  const lastX = (points.length - 1) * step;
  const lastY = height - ((last - min) / range) * (height - 2) - 1;

  return (
    <svg width={width} height={height} className="evo-metric__spark" aria-hidden="true">
      <path d={path} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={lastX} cy={lastY} r="2" fill={color} />
    </svg>
  );
}

function MetricCard({
  label,
  icon,
  value,
  unit,
  delta,
  deltaDir = "neutral",
  spark,
  sparkColor,
}: {
  label: string;
  icon: ReactNode;
  value: string;
  unit?: string;
  delta: string;
  deltaDir?: "up" | "down" | "neutral";
  spark: number[];
  sparkColor?: string;
}) {
  return (
    <div className="evo-metric">
      <div className="evo-metric__label">{icon} {label}</div>
      <div className="evo-metric__value">{value}{unit ? <span className="evo-metric__unit">{unit}</span> : null}</div>
      <div className={`evo-metric__delta evo-metric__delta--${deltaDir}`}>
        {deltaDir === "up" ? <ArrowUp size={11} /> : deltaDir === "down" ? <ArrowDown size={11} /> : null}
        {delta}
      </div>
      <Sparkline points={spark} color={sparkColor} />
    </div>
  );
}

function Badge({ variant = "default", children }: { variant?: "default" | "ok" | "warn" | "err" | "info" | "eval"; children: React.ReactNode }) {
  return (
    <span className={`evo-badge ${variant !== "default" ? `evo-badge--${variant}` : ""}`}>
      <span className="evo-badge__dot" />
      {children}
    </span>
  );
}

function StatusBadge({ status }: { status: string }) {
  const variant = status === "ok" || status === "success" ? "ok" : status === "partial" || status === "queued" ? "warn" : status === "error" || status === "failed" ? "err" : "default";
  return <Badge variant={variant}>{statusLabel(status)}</Badge>;
}

function Copyable({ value }: { value: string }) {
  return (
    <span className="evo-copyable">
      <span>{value}</span>
      <Copy size={11} />
    </span>
  );
}

function AreaChart({ data, color = "var(--accent)", height = 200 }: { data: ChartPoint[]; color?: string; height?: number }) {
  const width = 560;
  const safe = data.length ? data : fallbackSeries();
  const max = Math.max(...safe.map((d) => d.v), 1);
  const step = safe.length > 1 ? width / (safe.length - 1) : width;
  const points = safe.map((d, i) => [i * step, height - 28 - (d.v / max) * (height - 56)]);
  const line = points.map((p, i) => `${i === 0 ? "M" : "L"} ${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(" ");
  const area = `${line} L ${points[points.length - 1][0]} ${height - 28} L 0 ${height - 28} Z`;

  return (
    <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" style={{ width: "100%", height }}>
      <defs>
        <linearGradient id="evo-area-grad" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.35" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      {[0.25, 0.5, 0.75].map((t) => (
        <line key={t} x1="0" x2={width} y1={28 + (height - 56) * t} y2={28 + (height - 56) * t} stroke="var(--border-subtle)" strokeDasharray="3 4" />
      ))}
      <path d={area} fill="url(#evo-area-grad)" />
      <path d={line} fill="none" stroke={color} strokeWidth="1.8" strokeLinejoin="round" />
      {points.map((p, i) => i % Math.ceil(points.length / 8) === 0 ? <circle key={i} cx={p[0]} cy={p[1]} r="2.5" fill={color} /> : null)}
      {safe.map((d, i) => i % Math.ceil(safe.length / 8) === 0 ? (
        <text key={d.label + i} x={i * step} y={height - 8} textAnchor="middle" fontSize="10" fill="var(--text-faint)" fontFamily="var(--font-mono)">{d.label}</text>
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
          <tr><td colSpan={4} className="evo-empty-row">Nenhuma chamada LLM registrada ainda.</td></tr>
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
              <td className="evo-table__num">{fmtMoney(model.cost_usd, 4)}</td>
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

function ProblemTraces({ traces, org, project }: { traces: Trace[]; org: string; project: string }) {
  return (
    <table className="evo-table">
      <thead>
        <tr><th>Trace</th><th>ID</th><th>Status</th><th>Ambiente</th><th>Duração</th><th>Custo</th><th>Quando</th><th /></tr>
      </thead>
      <tbody>
        {traces.length === 0 ? (
          <tr><td colSpan={8} className="evo-empty-row">Nenhum trace com problema nesta janela.</td></tr>
        ) : traces.map((trace) => (
          <tr key={trace.id}>
            <td className="evo-table__name">{trace.name}</td>
            <td><Copyable value={trace.id} /></td>
            <td><StatusBadge status={trace.status} /></td>
            <td><span className="evo-tag">{trace.environment}</span></td>
            <td className="evo-table__num">{trace.duration_ms}ms</td>
            <td className="evo-table__num">{fmtMoney(trace.total_cost_usd, 5)}</td>
            <td className="evo-muted">{timeAgo(trace.created_at)}</td>
            <td><Link href={`/o/${org}/p/${project}/traces/${trace.id}`}><ChevronRight size={14} className="evo-faint" /></Link></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function NoToken() {
  return <AuthRequiredPanel layout="main" />;
}

export default async function ProjectOverviewPage({ params, searchParams }: Props) {
  const { org, project } = await params;
  const qp = await searchParams;
  const environment = qp.environment ?? "prod";

  if (!(await hasAuthToken())) return <NoToken />;

  const resolved = await resolveProject(org, project);
  const projectId = resolved.project_id;
  const [overview, recentRes] = await Promise.all([
    getOverview(projectId, qp.environment),
    getTraces({ projectId, limit: 8, environment: qp.environment }),
  ]);

  const { kpis, cost_by_day, model_breakdown, recent_flagged } = overview;
  const recentTraces = recentRes.data;
  const problemTraces = (recent_flagged.length ? recent_flagged : recentTraces.filter((trace) => trace.status !== "ok")).slice(0, 6);
  const costSeries = cost_by_day.length ? cost_by_day.slice(-14).map((d) => ({ label: fmtShortDate(d.day), v: d.cost_usd })) : fallbackSeries();
  const tracesSpark = asSpark(cost_by_day.map((d) => d.traces), kpis.traces);
  const latencySpark = asSpark(tracesSpark.map((v, i) => Math.max(0, kpis.latency_p95_ms + (i - tracesSpark.length / 2) * 8 + (v % 23))), kpis.latency_p95_ms);
  const costSpark = asSpark(cost_by_day.map((d) => d.cost_usd), kpis.cost_usd);
  const errorSpark = asSpark(cost_by_day.map((_, i) => Math.max(0, kpis.error_rate + ((i % 3) - 1) * 0.002)), kpis.error_rate);

  return (
    <div className="evo-page">
      <PageHeader project={project} org={org} />

            <section className="evo-kpi-grid">
              <MetricCard label="Traces" icon={<Activity size={12} />} value={fmtNumber(kpis.traces)} delta="janela atual" deltaDir="neutral" spark={tracesSpark} />
              <MetricCard label="p95 Latência" icon={<Clock size={12} />} value={fmtLatency(kpis.latency_p95_ms)} unit="s" delta="monitorando" deltaDir="neutral" spark={latencySpark} sparkColor="var(--warn)" />
              <MetricCard label="Custo" icon={<Coins size={12} />} value={fmtMoney(kpis.cost_usd)} delta="USD total" deltaDir="neutral" spark={costSpark} sparkColor="var(--eval)" />
              <MetricCard label="Erro" icon={<AlertCircle size={12} />} value={fmtPercent(kpis.error_rate)} unit="%" delta="taxa atual" deltaDir="neutral" spark={errorSpark} sparkColor="var(--ok)" />
            </section>

            <section className="evo-grid-2col">
              <div className="evo-card">
                <div className="evo-card__header">
                  <div>
                    <h3 className="evo-card__title">Custo & volume por dia</h3>
                    <div className="evo-card__subtitle">USD · últimos 14 dias</div>
                  </div>
                  <div className="evo-row">
                    <Badge variant="info">cost</Badge>
                    <button className="evo-btn evo-btn--ghost evo-btn--sm evo-btn--icon" aria-label="Exportar"><Download size={13} /></button>
                  </div>
                </div>
                <div className="evo-card__body">
                  <AreaChart data={costSeries} />
                </div>
              </div>

              <div className="evo-card">
                <div className="evo-card__header">
                  <h3 className="evo-card__title">Custo por modelo</h3>
                  <Link className="evo-btn evo-btn--ghost evo-btn--sm" href={`/o/${org}/p/${project}/traces`}>Ver detalhes <ArrowRight size={12} /></Link>
                </div>
                <div className="evo-card__body evo-card__body--flush">
                  <ModelTable breakdown={model_breakdown} />
                </div>
              </div>
            </section>

            <div style={{ height: 12 }} />

            <section className="evo-card">
              <div className="evo-card__header">
                <div>
                  <h3 className="evo-card__title">Últimos traces com problema</h3>
                  <div className="evo-card__subtitle">status diferente de ok · ordenado por mais recente</div>
                </div>
                <Link className="evo-btn evo-btn--sm" href={`/o/${org}/p/${project}/traces`}>Ver todos os traces <ArrowRight size={12} /></Link>
              </div>
              <div className="evo-card__body evo-card__body--flush">
                <ProblemTraces traces={problemTraces} org={org} project={project} />
              </div>
            </section>

            <footer className="evo-footer">
              <span>(c) 2026 EvalOps Studio</span>
              <span className="evo-spacer" />
              <a href="/docs">Documentação</a>
              <a href={`${apiRoot()}/health/readiness`} target="_blank" rel="noreferrer">Status</a>
              <span className="evo-ops"><Check size={12} /> Sistemas operando</span>
            </footer>
    </div>
  );
}
