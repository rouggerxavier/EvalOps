import Link from "next/link";
import { CheckCircle2, Coins, History, List, Play, Plus, Target } from "lucide-react";

import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { Badge } from "@/components/ui/Badge";
import { Copyable } from "@/components/ui/Copyable";
import { DistBars } from "@/components/ui/DistBars";
import { Metric } from "@/components/ui/Metric";
import { PageHeader } from "@/components/ui/PageHeader";
import { ScoreCell } from "@/components/ui/ScoreCell";
import {
  getEvaluationSummary,
  getProjectEvaluations,
  getRubricVersions,
  getRubrics,
  getTraces,
  hasAuthToken,
  resolveProject,
} from "@/lib/api";
import { safeErrorMessage } from "@/lib/safe-error";
import type { EvaluationRun, Rubric, RubricVersion } from "@/lib/types";

import { EvaluationsModals, type EvaluationRowSummary } from "./evaluations-modals";

type Props = {
  params: Promise<{ org: string; project: string }>;
  searchParams: Promise<{
    tab?: string;
    modal?: string;
    rubric?: string;
    created?: string;
    versioned?: string;
    published?: string;
    error?: string;
  }>;
};

type Tab = "active" | "runs" | "paused";
const TABS: Tab[] = ["active", "runs", "paused"];

const SEVEN_DAYS_MS = 7 * 24 * 60 * 60 * 1000;
const EVALUATION_RUNS_LIMIT = 100;

function parseTab(value: string | undefined): Tab {
  return TABS.includes(value as Tab) ? (value as Tab) : "active";
}

function buildDistribution(scores: number[], buckets = 6): number[] {
  const dist = Array<number>(buckets).fill(0);
  for (const s of scores) {
    const idx = Math.min(buckets - 1, Math.max(0, Math.floor(s * buckets)));
    dist[idx]++;
  }
  return dist;
}

function relTime(iso: string): string {
  const diff = Date.now() - Date.parse(iso);
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "agora";
  if (mins < 60) return `${mins}m`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h`;
  return `${Math.floor(hrs / 24)}d`;
}

function scoreColor(v: number | null): string {
  if (v === null) return "var(--fg-4)";
  if (v >= 0.85) return "var(--success)";
  if (v >= 0.7) return "var(--warning)";
  return "var(--danger)";
}

function withinLast7d(run: EvaluationRun): boolean {
  const t = Date.parse(run.created_at);
  return Number.isFinite(t) && Date.now() - t <= SEVEN_DAYS_MS;
}

function passRate(runs: EvaluationRun[]): number | null {
  const resolved = runs.filter((r) => r.passed !== null);
  if (resolved.length === 0) return null;
  return resolved.filter((r) => r.passed === true).length / resolved.length;
}

function fmtPct(v: number | null): string {
  if (v === null) return "—";
  return `${Math.round(v * 100)}%`;
}

function fmtCost(v: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: v > 0 && v < 0.01 ? 4 : 3,
    maximumFractionDigits: v > 0 && v < 0.01 ? 4 : 3,
  }).format(v);
}

type RubricFlavor = { type_label: "LLM-judge" | "Heurística"; judge_model: string | null };

function inferRubricFlavor(rubric: Rubric, latest: RubricVersion | null): RubricFlavor {
  const evaluators = latest?.parsed_spec?.evaluators ?? [];
  let judgeModel: string | null = null;
  let isLlm = false;
  for (const ev of evaluators) {
    const t = (ev.type ?? "").toLowerCase();
    if (t.includes("llm")) {
      isLlm = true;
      const cfg = ev.config ?? {};
      const m = (cfg as Record<string, unknown>)["model"];
      if (typeof m === "string" && !judgeModel) judgeModel = m;
    }
  }
  if (!isLlm) {
    const hint = `${rubric.slug} ${rubric.description ?? ""}`.toLowerCase();
    if (hint.includes("llm") || hint.includes("judge")) isLlm = true;
  }
  return { type_label: isLlm ? "LLM-judge" : "Heurística", judge_model: judgeModel };
}

export default async function EvaluationsPage({ params, searchParams }: Props) {
  const { org, project } = await params;
  const qp = await searchParams;
  const tab = parseTab(qp.tab);

  if (!(await hasAuthToken())) return <AuthRequiredPanel layout="main" />;

  const resolved = await resolveProject(org, project);

  const [summary, evalsRes, rubricsRes, tracesRes] = await Promise.all([
    getEvaluationSummary(resolved.project_id).catch(() => null),
    getProjectEvaluations(resolved.project_id, EVALUATION_RUNS_LIMIT),
    getRubrics(resolved.project_id),
    getTraces({ projectId: resolved.project_id, limit: 20 }),
  ]);

  const runs = [...evalsRes.data].sort(
    (a, b) => Date.parse(b.created_at) - Date.parse(a.created_at),
  );
  const rubrics = rubricsRes.data;
  const traces = tracesRes.data;

  const rubricMap = new Map<string, Rubric>(rubrics.map((r) => [r.id, r]));

  const versionsByRubric = new Map<string, RubricVersion[]>();
  await Promise.all(
    rubrics.map(async (r) => {
      try {
        const res = await getRubricVersions(r.id);
        versionsByRubric.set(r.id, res.data);
      } catch {
        versionsByRubric.set(r.id, []);
      }
    }),
  );

  const byRubric = new Map<string, { rubric: Rubric; runs: EvaluationRun[] }>();
  for (const run of runs) {
    const rubric = rubricMap.get(run.rubric_id);
    if (!rubric) continue;
    if (!byRubric.has(run.rubric_id)) byRubric.set(run.rubric_id, { rubric, runs: [] });
    byRubric.get(run.rubric_id)!.runs.push(run);
  }
  const evalRows = rubrics.map((rubric) => byRubric.get(rubric.id) ?? { rubric, runs: [] });

  const totalRuns7d = summary?.runs_7d ?? runs.filter(withinLast7d).length;
  const activeRubrics = summary?.active_rubrics ?? rubrics.length;
  const overallPassRate = summary?.pass_rate ?? passRate(runs);
  const costUsd = summary?.cost_usd ?? runs.reduce((s, r) => s + r.cost_usd, 0);

  const baseUrl = `/o/${org}/p/${project}/evaluations`;
  const tabHref = (t: string) => `${baseUrl}?tab=${t}`;
  const modalHref = (modal: string, extra: Record<string, string> = {}) => {
    const s = new URLSearchParams({ tab, modal, ...extra });
    return `${baseUrl}?${s.toString()}`;
  };

  const queryError = qp.error ? safeErrorMessage(qp.error, "Falha ao executar ação.") : null;
  const successMessage = qp.created
    ? "Run de avaliação criada com sucesso."
    : qp.versioned || qp.published
      ? "Rubric publicada."
      : null;

  const drawerRubricId = qp.modal === "drawer" || qp.modal === "publish" ? qp.rubric ?? null : null;
  let drawerRow: EvaluationRowSummary | null = null;
  if (drawerRubricId) {
    const row = evalRows.find((r) => r.rubric.id === drawerRubricId);
    if (row) {
      // Partial runs score only part of the evidence: same rule as the API report.
      const scores = row.runs.filter((r) => r.passed !== null).map((r) => r.aggregate_score).filter((s): s is number => s !== null);
      const avg = scores.length ? scores.reduce((a, b) => a + b, 0) / scores.length : null;
      const versions = versionsByRubric.get(row.rubric.id) ?? [];
      const latest = versions.find((v) => v.version === row.rubric.current_version) ?? versions[0] ?? null;
      const flavor = inferRubricFlavor(row.rubric, latest);
      drawerRow = {
        rubric_id: row.rubric.id,
        slug: row.rubric.slug,
        description: row.rubric.description,
        current_version: row.rubric.current_version,
        threshold: row.rubric.threshold,
        type_label: flavor.type_label,
        judge_model: flavor.judge_model,
        avg_score: avg,
        runs_7d: row.runs.filter(withinLast7d).length,
        pass_rate: passRate(row.runs),
        yaml_source: latest?.yaml_source ?? null,
      };
    }
  }

  return (
    <div className="page">
      <PageHeader
        eyebrow="Qualidade"
        title="Avaliações"
        subtitle="LLM-as-judge e heurísticas executadas sobre traces de produção."
        actions={
          <>
            <Link href={modalHref("run")} className="btn btn--sm">
              <Play size={12} /> Rodar agora
            </Link>
            <Link href={`/o/${org}/p/${project}/rubrics`} className="btn btn--sm" data-testid="evaluations-rubrics-link">
              <List size={12} /> Ver rubricas
            </Link>
            <Link href={modalHref("create")} className="btn btn--sm btn--primary">
              <Plus size={12} /> Nova rubrica
            </Link>
          </>
        }
      />

      {queryError && (
        <div
          role="alert"
          style={{
            padding: "10px 14px",
            background: "color-mix(in oklab, var(--danger) 14%, transparent)",
            border: "1px solid color-mix(in oklab, var(--danger) 40%, transparent)",
            borderRadius: 6,
            color: "var(--danger)",
            fontSize: 13,
            marginBottom: 12,
          }}
        >
          {queryError}
        </div>
      )}
      {successMessage && (
        <div
          style={{
            padding: "10px 14px",
            background: "color-mix(in oklab, var(--success) 14%, transparent)",
            border: "1px solid color-mix(in oklab, var(--success) 40%, transparent)",
            borderRadius: 6,
            color: "var(--success)",
            fontSize: 13,
            marginBottom: 12,
          }}
        >
          {successMessage}
        </div>
      )}

      <section className="kpi-grid" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
        <Metric
          label="Rubricas ativas"
          icon={<Target size={12} />}
          value={activeRubrics.toLocaleString("pt-BR")}
          delta="GET /v1/projects/.../evaluations/summary"
        />
        <Metric
          label="Runs 7d"
          icon={<History size={12} />}
          value={totalRuns7d.toLocaleString("pt-BR")}
          delta="todas rubricas"
        />
        <Metric
          label="Taxa de aprovação"
          icon={<CheckCircle2 size={12} />}
          value={fmtPct(overallPassRate)}
          delta="média ponderada"
          deltaTone="up"
        />
        <Metric
          label="Custo de avaliação"
          icon={<Coins size={12} />}
          value={fmtCost(costUsd)}
          delta="USD · 7d"
        />
      </section>

      <nav className="tabs" aria-label="Filtros de avaliações">
        <Link href={tabHref("active")} className={`tab${tab === "active" ? " is-active" : ""}`}>
          <Target size={11} /> Ativas
          <span className="tab__count">{evalRows.length}</span>
        </Link>
        <Link href={tabHref("runs")} className={`tab${tab === "runs" ? " is-active" : ""}`}>
          <History size={11} /> Runs recentes
          <span className="tab__count">{runs.length.toLocaleString("pt-BR")}</span>
        </Link>
        <Link href={tabHref("paused")} className={`tab${tab === "paused" ? " is-active" : ""}`}>
          Pausadas
          <span className="tab__count">0</span>
        </Link>
      </nav>

      {tab === "active" && (
        <div className="table-wrap">
          {evalRows.length === 0 ? (
            <div className="empty">
              <div className="empty__icon"><Target size={18} /></div>
              <div className="empty__title">Nenhuma rubrica cadastrada</div>
              <div className="empty__desc">Crie uma rubric YAML antes de rodar avaliações sobre traces.</div>
              <Link href={modalHref("create")} className="btn btn--sm btn--primary" style={{ marginTop: 12 }}>
                <Plus size={12} /> Nova rubrica
              </Link>
            </div>
          ) : (
            <table className="t">
              <thead>
                <tr>
                  <th>Avaliação</th>
                  <th>Tipo</th>
                  <th>Judge model</th>
                  <th className="t__num">Runs 7d</th>
                  <th>Score médio</th>
                  <th>Distribuição (0 → 1)</th>
                  <th>Pass rate</th>
                  <th>Última</th>
                  <th style={{ width: 32 }} />
                </tr>
              </thead>
              <tbody>
                {evalRows.map(({ rubric, runs: rubricRuns }) => {
                  const scores = rubricRuns
                    .filter((r) => r.passed !== null)
                    .map((r) => r.aggregate_score)
                    .filter((s): s is number => s !== null);
                  const avg = scores.length ? scores.reduce((a, b) => a + b, 0) / scores.length : null;
                  const dist = buildDistribution(scores);
                  const lastRun = rubricRuns[0];
                  const rubricRuns7d = rubricRuns.filter(withinLast7d).length;
                  const rubricPassRate = passRate(rubricRuns);
                  const versions = versionsByRubric.get(rubric.id) ?? [];
                  const latest = versions.find((v) => v.version === rubric.current_version) ?? versions[0] ?? null;
                  const flavor = inferRubricFlavor(rubric, latest);
                  const drawerLink = modalHref("drawer", { rubric: rubric.id });
                  return (
                    <tr key={rubric.id} className="t__row-link">
                      <td>
                        <Link href={drawerLink} style={{ display: "flex", flexDirection: "column", gap: 2, color: "inherit" }}>
                          <span className="t__name">{rubric.slug}</span>
                          <span className="t__faint" style={{ fontSize: 11 }}>{rubric.description ?? `eval_${rubric.slug}`}</span>
                        </Link>
                      </td>
                      <td>
                        <Badge variant={flavor.type_label === "LLM-judge" ? "eval" : "info"}>
                          {flavor.type_label === "LLM-judge" ? "LLM-as-judge" : "Heurística"}
                        </Badge>
                      </td>
                      <td className="t__mono t__muted">{flavor.judge_model ?? "—"}</td>
                      <td className="t__num">{rubricRuns7d.toLocaleString("pt-BR")}</td>
                      <td>
                        {avg === null ? (
                          <span className="t__faint">—</span>
                        ) : (
                          <span className="mono" style={{ fontSize: 13, color: scoreColor(avg) }}>{avg.toFixed(2)}</span>
                        )}
                      </td>
                      <td>{scores.length ? <DistBars dist={dist} /> : <span className="t__faint">—</span>}</td>
                      <td>
                        <span
                          className="mono"
                          style={{
                            fontSize: 12,
                            color: rubricPassRate !== null && rubricPassRate >= rubric.threshold ? "var(--success)" : "var(--warning)",
                          }}
                        >
                          {fmtPct(rubricPassRate)}
                        </span>
                        <span className="t__faint mono" style={{ fontSize: 10, marginLeft: 4 }}>
                          / threshold {rubric.threshold.toFixed(2)}
                        </span>
                      </td>
                      <td className="t__faint" style={{ fontSize: 11 }}>
                        {lastRun ? `${relTime(lastRun.created_at)} atrás` : "—"}
                      </td>
                      <td>
                        <Link href={drawerLink} aria-label={`Abrir detalhes de ${rubric.slug}`} className="t__chev-link">
                          ›
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      )}

      {tab === "runs" && (
        <div className="table-wrap">
          {runs.length === 0 ? (
            <div className="empty">
              <div className="empty__icon"><History size={18} /></div>
              <div className="empty__title">Nenhuma run ainda</div>
              <div className="empty__desc">
                {rubrics.length === 0
                  ? "Crie uma rubric YAML antes de rodar avaliações."
                  : traces.length === 0
                    ? "Capture um trace antes de rodar avaliações."
                    : "Use uma rubric versionada e um trace elegível para iniciar a primeira run."}
              </div>
              {rubrics.length > 0 && traces.length > 0 && (
                <Link href={modalHref("run")} className="btn btn--sm btn--primary" style={{ marginTop: 12 }}>
                  <Play size={12} /> Rodar agora
                </Link>
              )}
            </div>
          ) : (
            <table className="t">
              <thead>
                <tr>
                  <th>Trace</th>
                  <th>Rubric</th>
                  <th>Status</th>
                  <th>Score</th>
                  <th className="t__num">Custo</th>
                  <th>Quando</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => {
                  const rubric = rubricMap.get(run.rubric_id);
                  const traceHref = `/o/${org}/p/${project}/traces/${run.trace_id}`;
                  return (
                    <tr key={run.id}>
                      <td><Copyable value={run.trace_id} /></td>
                      <td>
                        <Link href={traceHref} className="t__mono t__muted" style={{ fontSize: 12 }}>
                          {rubric ? `${rubric.slug} v${run.rubric_version}` : run.rubric_id.slice(0, 12)}
                        </Link>
                      </td>
                      <td>
                        {run.passed === true ? (
                          <Badge variant="ok">passou</Badge>
                        ) : run.passed === false ? (
                          <Badge variant="err">falhou</Badge>
                        ) : (
                          <Badge>{run.status === "completed" ? "sem veredito" : run.status === "error" ? "erro" : run.status}</Badge>
                        )}
                      </td>
                      <td>
                        {run.aggregate_score === null ? (
                          <span className="t__faint">—</span>
                        ) : (
                          <ScoreCell value={run.aggregate_score} />
                        )}
                      </td>
                      <td className="t__num t__muted">${run.cost_usd.toFixed(6)}</td>
                      <td className="t__faint" style={{ fontSize: 11 }}>{relTime(run.created_at)} atrás</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      )}

      {tab === "paused" && (
        <div className="empty">
          <div className="empty__icon"><Target size={18} /></div>
          <div className="empty__title">Nenhuma avaliação pausada</div>
          <div className="empty__desc">
            Avaliações são pausadas automaticamente quando custo excede o limite ou quando o judge model fica indisponível.
          </div>
        </div>
      )}

      <EvaluationsModals
        org={org}
        project={project}
        projectId={resolved.project_id}
        rubrics={rubrics.map((r) => ({ id: r.id, slug: r.slug, current_version: r.current_version }))}
        traces={traces.map((t) => ({ id: t.id, name: t.name, environment: t.environment }))}
        drawerRow={drawerRow}
      />
    </div>
  );
}
