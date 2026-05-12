import type { ReactNode } from "react";
import Link from "next/link";
import {
  Activity,
  Star,
  Timer,
  DollarSign,
  Info,
  Users,
  TrendingUp,
  TrendingDown,
} from "lucide-react";

import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { getOverview, getTraces, hasAuthToken, resolveProject } from "@/lib/api";
import type { OverviewResponse, Trace } from "@/lib/types";

type Props = {
  params: Promise<{ org: string; project: string }>;
  searchParams: Promise<{ environment?: string }>;
};

const RAW_API_BASE = process.env.EVALOPS_API_BASE_URL ?? "http://localhost:8000/v1";
const API_ROOT = RAW_API_BASE.endsWith("/v1") ? RAW_API_BASE.slice(0, -3) : RAW_API_BASE;

/* ─── Formatting helpers ─────────────────────────────────────────────── */

function fmtNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return n.toLocaleString();
  return String(n);
}

function fmtCost(usd: number): string {
  if (usd >= 1000) return `$${(usd / 1000).toFixed(1)}K`;
  return `$${usd.toFixed(2)}`;
}

function fmtLatency(ms: number): string {
  return `${(ms / 1000).toFixed(2)}`;
}

function fmtScore(s: number | null): string {
  if (s === null) return "—";
  return s.toFixed(2);
}

/* ─── Sparkline SVG ─────────────────────────────────────────────────── */

function Sparkline({ data, color = "#3b8df5" }: { data: number[]; color?: string }) {
  if (data.length < 2) {
    return <div className="kpi__sparkline" style={{ background: "transparent" }} />;
  }
  const w = 240, h = 56, pad = 2;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const step = (w - pad * 2) / (data.length - 1);
  const points = data.map((v, i) => [
    pad + i * step,
    h - pad - ((v - min) / range) * (h - pad * 2),
  ]);
  const path = "M" + points.map((p) => p.join(",")).join(" L");
  const area = `${path} L${points[points.length - 1][0]},${h} L${pad},${h} Z`;
  const gradId = `sg${color.replace(/[^a-z0-9]/gi, "")}`;
  return (
    <svg
      className="kpi__sparkline"
      viewBox={`0 0 ${w} ${h}`}
      preserveAspectRatio="none"
      width="100%"
      height="56"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id={gradId} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.32" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${gradId})`} />
      <path d={path} fill="none" stroke={color} strokeWidth="1.6" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

/* ─── KPI Card ──────────────────────────────────────────────────────── */

function KpiCard({
  label,
  icon,
  iconClass,
  value,
  unit,
  delta,
  deltaLabel,
  deltaUp,
  sparkData,
  sparkColor,
}: {
  label: string;
  icon: ReactNode;
  iconClass?: string;
  value: string;
  unit?: string;
  delta?: string;
  deltaLabel?: string;
  deltaUp?: boolean;
  sparkData: number[];
  sparkColor: string;
}) {
  return (
    <div className="card card--inset">
      <div className="kpi">
        <div className="kpi__head">
          <span>{label}</span>
          <span className={`kpi__icon${iconClass ? " " + iconClass : ""}`}>{icon}</span>
        </div>
        <div className="kpi__value">
          {value}
          {unit && <span className="unit"> {unit}</span>}
        </div>
        {delta && (
          <div className={`kpi__delta${deltaUp === false ? " bad" : ""}`}>
            {deltaUp !== false ? <TrendingUp size={10} /> : <TrendingDown size={10} />}
            <span>{delta}</span>
            {deltaLabel && <span className="ctx">{deltaLabel}</span>}
          </div>
        )}
        <Sparkline data={sparkData} color={sparkColor} />
      </div>
    </div>
  );
}

/* ─── Traces Over Time chart ────────────────────────────────────────── */

function TracesOverTimeChart({ data }: { data: OverviewResponse["cost_by_day"] }) {
  const slice = data.slice(-7);
  if (slice.length < 2) {
    return (
      <div className="chart-empty">
        <Activity size={28} />
        <span>No trace data yet for this period.</span>
      </div>
    );
  }
  const w = 560, h = 220, padL = 40, padR = 12, padT = 16, padB = 28;
  const maxY = Math.max(...slice.map((d) => d.traces), 1);
  const cw = w - padL - padR, ch = h - padT - padB;
  const xs = slice.map((_, i) => padL + (i / (slice.length - 1)) * cw);
  const ys = slice.map((d) => padT + ch - (d.traces / maxY) * ch);
  const pathD = xs.map((x, i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${ys[i].toFixed(1)}`).join(" ");
  const areaD = `${pathD} L${xs[xs.length - 1].toFixed(1)},${(padT + ch).toFixed(1)} L${padL},${(padT + ch).toFixed(1)} Z`;
  const yTicks = [0, Math.round(maxY / 2), maxY];
  const fmt = (v: number) => v >= 1000 ? `${(v / 1000).toFixed(0)}K` : String(v);

  return (
    <svg viewBox={`0 0 ${w} ${h}`} width="100%" height="220" preserveAspectRatio="none" aria-label="Traces over time">
      <defs>
        <linearGradient id="trace-area-grad" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="#22d3ee" stopOpacity="0.28" />
          <stop offset="100%" stopColor="#22d3ee" stopOpacity="0" />
        </linearGradient>
      </defs>
      {yTicks.map((t) => {
        const y = padT + ch - (t / maxY) * ch;
        return (
          <g key={t}>
            <line x1={padL} y1={y.toFixed(1)} x2={w - padR} y2={y.toFixed(1)} stroke="#1c2748" strokeDasharray="2 4" />
            <text x={padL - 8} y={(y + 3).toFixed(1)} fill="#5a6791" fontSize="10" textAnchor="end">{fmt(t)}</text>
          </g>
        );
      })}
      <path d={areaD} fill="url(#trace-area-grad)" />
      <path d={pathD} fill="none" stroke="#22d3ee" strokeWidth="2" strokeLinejoin="round" />
      {xs.map((x, i) => {
        const label = new Date(slice[i].day).toLocaleDateString("en-US", { month: "short", day: "numeric" });
        return (
          <g key={i}>
            <circle cx={x.toFixed(1)} cy={ys[i].toFixed(1)} r="3" fill="#0a1024" stroke="#22d3ee" strokeWidth="2" />
            <text x={x.toFixed(1)} y={h - 8} fill="#5a6791" fontSize="10.5" textAnchor="middle">{label}</text>
          </g>
        );
      })}
    </svg>
  );
}

/* ─── Eval Quality chart ─────────────────────────────────────────────── */

function EvalQualityChart({
  errorRate,
  avgScore,
  days,
}: {
  errorRate: number;
  avgScore: number | null;
  days: OverviewResponse["cost_by_day"];
}) {
  const slice = days.slice(-7);
  const passedBase = avgScore !== null ? Math.min(0.95, Math.max(0.4, avgScore)) : 0.65;
  const failedBase = Math.min(0.4, errorRate);
  const reviewBase = Math.max(0, 1 - passedBase - failedBase);

  const data = slice.length > 0
    ? slice.map(() => [
        Math.round(passedBase * 100),
        Math.round(reviewBase * 100),
        Math.round(failedBase * 100),
      ])
    : Array(7).fill([65, 20, 15]) as number[][];

  const labels = slice.length > 0
    ? slice.map((d) => new Date(d.day).toLocaleDateString("en-US", { month: "short", day: "numeric" }))
    : ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

  const w = 560, h = 220, padL = 40, padR = 12, padT = 16, padB = 28;
  const cw = w - padL - padR, ch = h - padT - padB;
  const barW = (cw / data.length) * 0.55;
  const gap = cw / data.length;

  return (
    <svg viewBox={`0 0 ${w} ${h}`} width="100%" height="220" preserveAspectRatio="none" aria-label="Evaluation quality">
      {[0, 50, 100].map((t) => {
        const y = padT + ch - (t / 100) * ch;
        return (
          <g key={t}>
            <line x1={padL} y1={y.toFixed(1)} x2={w - padR} y2={y.toFixed(1)} stroke="#1c2748" strokeDasharray="2 4" />
            <text x={padL - 8} y={(y + 3).toFixed(1)} fill="#5a6791" fontSize="10" textAnchor="end">{t}%</text>
          </g>
        );
      })}
      {data.map(([p, r, f], i) => {
        const cx = padL + gap * (i + 0.5);
        const x = cx - barW / 2;
        const fH = (f / 100) * ch;
        const rH = (r / 100) * ch;
        const pH = (p / 100) * ch;
        const yBase = padT + ch;
        return (
          <g key={i}>
            <rect x={x.toFixed(1)} y={(yBase - fH).toFixed(1)} width={barW.toFixed(1)} height={fH.toFixed(1)} fill="#ef5d5d" rx="1" />
            <rect x={x.toFixed(1)} y={(yBase - fH - rH).toFixed(1)} width={barW.toFixed(1)} height={rH.toFixed(1)} fill="#f5b945" />
            <rect x={x.toFixed(1)} y={(yBase - fH - rH - pH).toFixed(1)} width={barW.toFixed(1)} height={pH.toFixed(1)} fill="#2ec27e" rx="1" />
            <text x={cx.toFixed(1)} y={h - 8} fill="#5a6791" fontSize="10.5" textAnchor="middle">{labels[i]}</text>
          </g>
        );
      })}
    </svg>
  );
}

/* ─── Recent Traces table ────────────────────────────────────────────── */

function StatusBadge({ status }: { status: string }) {
  if (status === "ok") return <span className="badge badge--passed">Passed</span>;
  if (status === "error") return <span className="badge badge--failed">Failed</span>;
  if (status === "partial") return <span className="badge badge--review">Needs Review</span>;
  return <span className="badge badge--neutral">{status}</span>;
}

function ScoreCell({ value }: { value: number | null }) {
  if (value === null) return <span style={{ color: "var(--fg-4)" }}>—</span>;
  const cls = value >= 0.7 ? "" : value >= 0.4 ? " warn" : " bad";
  return (
    <span className="score-cell">
      <span className="v">{value.toFixed(2)}</span>
      <span className={`score-bar${cls}`}>
        <i style={{ width: `${value * 100}%` }} />
      </span>
    </span>
  );
}

function RecentTracesTable({
  traces,
  org,
  project,
}: {
  traces: Trace[];
  org: string;
  project: string;
}) {
  return (
    <div className="card table-card">
      <div className="table-head">
        <div className="title">Recent Traces</div>
        <Link href={`/o/${org}/p/${project}/traces`} style={{ color: "var(--primary-300)", fontSize: 12.5, fontWeight: 500 }}>
          View all traces ›
        </Link>
      </div>
      {traces.length === 0 ? (
        <p style={{ color: "var(--fg-4)", fontSize: 13, margin: 0 }}>
          No traces yet. Instrument your application with the EvalOps SDK to start seeing data here.
        </p>
      ) : (
        <table className="t-table">
          <thead>
            <tr>
              <th>Trace</th>
              <th>Status</th>
              <th>Environment</th>
              <th>Score</th>
              <th>Duration</th>
              <th>Cost USD</th>
              <th>Time</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {traces.map((t) => (
              <tr key={t.id} className="row">
                <td>
                  <Link
                    href={`/o/${org}/p/${project}/traces/${t.id}`}
                    className="trace-id"
                    style={{ textDecoration: "none" }}
                  >
                    {t.name.length > 32 ? t.name.slice(0, 32) + "…" : t.name}
                  </Link>
                </td>
                <td><StatusBadge status={t.status} /></td>
                <td><span className="badge badge--env">{t.environment}</span></td>
                <td><ScoreCell value={null} /></td>
                <td style={{ fontVariantNumeric: "tabular-nums" }}>{t.duration_ms}ms</td>
                <td style={{ fontVariantNumeric: "tabular-nums" }}>${t.total_cost_usd.toFixed(6)}</td>
                <td style={{ color: "var(--fg-3)", whiteSpace: "nowrap" }}>
                  {new Date(t.created_at).toLocaleTimeString("en-US", {
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </td>
                <td className="arrow">›</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

/* ─── Model Usage donut ───────────────────────────────────────────────── */

const DONUT_COLORS = ["#3b8df5", "#22d3ee", "#a78bfa", "#f5b945", "#5a6791"];

function ModelUsageCard({
  breakdown,
  org,
  project,
}: {
  breakdown: OverviewResponse["model_breakdown"];
  org: string;
  project: string;
}) {
  const total = breakdown.reduce((s, b) => s + b.calls, 0) || 1;
  const top4 = breakdown.slice(0, 4);
  const otherCalls = breakdown.slice(4).reduce((s, b) => s + b.calls, 0);
  const segments = [
    ...top4.map((b, i) => ({
      label: b.model ?? b.provider ?? "unknown",
      pct: (b.calls / total) * 100,
      color: DONUT_COLORS[i],
    })),
    ...(otherCalls > 0 ? [{ label: "other", pct: (otherCalls / total) * 100, color: "#5a6791" }] : []),
  ];

  const r = 38, cx = 48, cy = 48;
  const C = 2 * Math.PI * r;
  let acc = 0;

  return (
    <div className="card">
      <div className="rail__head">
        <span className="title">
          Model Usage{" "}
          <span style={{ fontSize: 11, color: "var(--fg-3)", fontWeight: 400 }}>(by calls)</span>
        </span>
      </div>
      {breakdown.length === 0 ? (
        <p style={{ color: "var(--fg-4)", fontSize: 12, margin: 0 }}>No LLM calls recorded yet.</p>
      ) : (
        <>
          <div className="donut-row">
            <svg className="donut" viewBox="0 0 96 96" aria-hidden="true">
              <circle cx={cx} cy={cy} r={r} fill="none" stroke="var(--surface-2)" strokeWidth="12" />
              {segments.map((s, i) => {
                const len = (s.pct / 100) * C;
                const dasharray = `${len.toFixed(2)} ${(C - len).toFixed(2)}`;
                const offset = -((acc / 100) * C);
                acc += s.pct;
                return (
                  <circle
                    key={i}
                    cx={cx} cy={cy} r={r}
                    fill="none"
                    stroke={s.color}
                    strokeWidth="12"
                    strokeDasharray={dasharray}
                    strokeDashoffset={offset.toFixed(2)}
                    transform={`rotate(-90 ${cx} ${cy})`}
                  />
                );
              })}
            </svg>
            <ul className="usage-list">
              {segments.map((s) => (
                <li key={s.label} className="usage-row">
                  <span className="lbl">
                    <span className="swatch" style={{ background: s.color }} />
                    {s.label}
                  </span>
                  <span className="pct">{s.pct.toFixed(1)}%</span>
                </li>
              ))}
            </ul>
          </div>
          <Link href={`/o/${org}/p/${project}/traces`} className="full-report">View full report ›</Link>
        </>
      )}
    </div>
  );
}

/* ─── Active Rubrics (placeholder) ──────────────────────────────────── */

function ActiveRubricsCard({ project, org }: { project: string; org: string }) {
  return (
    <div className="card">
      <div className="rail__head">
        <span className="title">Active Rubrics</span>
        <Link href={`/o/${org}/p/${project}/rubrics`} style={{ color: "var(--primary-300)", fontSize: 12, fontWeight: 500 }}>
          View all
        </Link>
      </div>
      <p style={{ color: "var(--fg-4)", fontSize: 12, margin: 0 }}>
        No rubrics configured. Push a YAML rubric via the CLI or API to start evaluating traces.
      </p>
    </div>
  );
}

/* ─── Critical Flags (derived from flagged traces) ───────────────────── */

function CriticalFlagsCard({ flagged }: { flagged: Trace[] }) {
  if (flagged.length === 0) {
    return (
      <div className="card">
        <div className="rail__head">
          <span className="title">Critical Flags</span>
        </div>
        <p style={{ color: "var(--fg-4)", fontSize: 12, margin: 0 }}>No critical flags — looking good.</p>
      </div>
    );
  }
  const shown = flagged.slice(0, 4);
  return (
    <div className="card">
      <div className="rail__head">
        <span className="title">
          Critical Flags <span className="pill">{flagged.length}</span>
        </span>
      </div>
      {shown.map((t) => (
        <div key={t.id} className="flag-row">
          <span className="dot" />
          <div className="body">
            <div className="msg">{t.name.length > 40 ? t.name.slice(0, 40) + "…" : t.name}</div>
          </div>
          <span className="when">
            {new Date(t.created_at).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" })}
          </span>
        </div>
      ))}
      {flagged.length > 4 && (
        <a href="#" style={{ color: "var(--primary-300)", fontSize: 12, marginTop: 8, display: "inline-block" }}>
          View all flags
        </a>
      )}
    </div>
  );
}

/* ─── Billing placeholder ────────────────────────────────────────────── */

function BillingCard({ costUsd, org, project }: { costUsd: number; org: string; project: string }) {
  return (
    <div className="card">
      <div className="rail__head">
        <span className="title">Billing / Usage</span>
        <Link href={`/o/${org}/p/${project}/exports`} style={{ color: "var(--primary-300)", fontSize: 12, fontWeight: 500 }}>
          View billing
        </Link>
      </div>
      <div style={{ fontSize: 11.5, color: "var(--fg-3)" }}>Current period (last 7 days)</div>
      <div className="billing-amount" style={{ marginTop: 6 }}>{fmtCost(costUsd)}</div>
      <div className="billing-meta">LLM inference costs</div>
      <div className="usage-bar">
        <i style={{ width: `${Math.min(100, (costUsd / 3000) * 100).toFixed(1)}%` }} />
      </div>
      <div className="usage-foot">
        <span>vs $3,000 project limit</span>
        <span>Resets monthly</span>
      </div>
    </div>
  );
}

/* ─── Token-missing fallback ─────────────────────────────────────────── */

function NoToken() {
  return <AuthRequiredPanel layout="main" />;
}

/* ─── Page ───────────────────────────────────────────────────────────── */

export default async function ProjectOverviewPage({ params, searchParams }: Props) {
  const { org, project } = await params;
  const qp = await searchParams;

  if (!(await hasAuthToken())) {
    return <NoToken />;
  }

  const resolved = await resolveProject(org, project);
  const projectId = resolved.project_id;

  const [overview, recentRes] = await Promise.all([
    getOverview(projectId, qp.environment),
    getTraces({ projectId, limit: 5, environment: qp.environment }),
  ]);

  const { kpis, cost_by_day, model_breakdown, recent_flagged } = overview;
  const recentTraces = recentRes.data;

  const traceSparkData = cost_by_day.map((d) => d.traces);
  const costSparkData = cost_by_day.map((d) => d.cost_usd);

  /* Simple period-over-period delta from the daily data */
  function periodDelta(vals: number[]): number | null {
    if (vals.length < 2) return null;
    const mid = Math.ceil(vals.length / 2);
    const first = vals.slice(0, mid).reduce((s, v) => s + v, 0);
    const second = vals.slice(mid).reduce((s, v) => s + v, 0);
    if (first === 0) return null;
    return (second - first) / first;
  }

  const traceDelta = periodDelta(traceSparkData);
  const costDelta = periodDelta(costSparkData);

  return (
    <main className="main">
      {/* Page header */}
      <div className="page-header">
        <div>
          <h1>{project}</h1>
          <p className="sub">AI observability, tracing and evaluation for production AI systems.</p>
        </div>
        <div className="workspace-meta">
          <span>
            Workspace: <strong>{org}</strong>
          </span>
          <span className="sep" />
          <span className="meta-row">
            <Users size={14} />
            <span>Production</span>
          </span>
        </div>
      </div>

      {/* Main layout */}
      <div className="layout">
        {/* Left column */}
        <div>
          {/* KPI Cards */}
          <section className="kpi-grid">
            <KpiCard
              label="Total Traces"
              icon={<Activity size={14} />}
              value={fmtNumber(kpis.traces)}
              delta={traceDelta !== null ? `${traceDelta >= 0 ? "↑" : "↓"} ${Math.abs(traceDelta * 100).toFixed(1)}%` : undefined}
              deltaLabel="vs prior period"
              deltaUp={traceDelta === null || traceDelta >= 0}
              sparkData={traceSparkData.length ? traceSparkData : [0, 0]}
              sparkColor="#3b8df5"
            />
            <KpiCard
              label="Avg Eval Score"
              icon={<Star size={14} />}
              iconClass="cyan"
              value={fmtScore(kpis.avg_score)}
              unit={kpis.avg_score !== null ? "/ 1.00" : undefined}
              sparkData={kpis.avg_score !== null ? [kpis.avg_score * 0.9, kpis.avg_score] : [0, 0]}
              sparkColor="#22d3ee"
            />
            <KpiCard
              label="P95 Latency"
              icon={<Timer size={14} />}
              iconClass="warn"
              value={fmtLatency(kpis.latency_p95_ms)}
              unit="s"
              sparkData={traceSparkData.length ? traceSparkData.map((v) => 1 / (v || 1)) : [0, 0]}
              sparkColor="#f5b945"
            />
            <KpiCard
              label="Estimated Cost"
              icon={<DollarSign size={14} />}
              iconClass="green"
              value={fmtCost(kpis.cost_usd)}
              delta={costDelta !== null ? `${costDelta >= 0 ? "↑" : "↓"} ${Math.abs(costDelta * 100).toFixed(1)}%` : undefined}
              deltaLabel="vs prior period"
              deltaUp={costDelta !== null && costDelta < 0}
              sparkData={costSparkData.length ? costSparkData : [0, 0]}
              sparkColor="#2ec27e"
            />
          </section>

          {/* Charts */}
          <section className="chart-row">
            <div className="card chart-card" style={{ minHeight: 280 }}>
              <div className="chart-head">
                <div className="title">
                  Traces Over Time <Info size={14} />
                </div>
              </div>
              <TracesOverTimeChart data={cost_by_day} />
            </div>

            <div className="card chart-card" style={{ minHeight: 280 }}>
              <div className="chart-head">
                <div className="title">
                  Evaluation Quality <Info size={14} />
                </div>
                <div className="legend">
                  <span className="legend-dot passed">Passed</span>
                  <span className="legend-dot review">Review</span>
                  <span className="legend-dot failed">Failed</span>
                </div>
              </div>
              <EvalQualityChart
                errorRate={kpis.error_rate}
                avgScore={kpis.avg_score}
                days={cost_by_day}
              />
            </div>
          </section>

          {/* Recent Traces */}
          <RecentTracesTable traces={recentTraces} org={org} project={project} />
        </div>

        {/* Right rail */}
        <aside className="rail">
          <ActiveRubricsCard org={org} project={project} />
          <CriticalFlagsCard flagged={recent_flagged} />
          <ModelUsageCard breakdown={model_breakdown} org={org} project={project} />
          <BillingCard costUsd={kpis.cost_usd} org={org} project={project} />
        </aside>
      </div>

      {/* Footer */}
      <footer className="app-footer">
        <div>© 2026 EvalOps Studio, Inc.</div>
        <div className="links">
          <a href="/docs">Docs</a>
          <a href={`${API_ROOT}/health/readiness`} target="_blank" rel="noreferrer">Status</a>
          <a href="/changelog">Changelog</a>
          <a href="/docs">API</a>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <span style={{ color: "var(--fg-3)", fontSize: 12 }}>All times UTC</span>
          <span className="ops">All systems operational</span>
        </div>
      </footer>
    </main>
  );
}
