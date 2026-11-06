import Link from "next/link";
import { AlertTriangle, CheckCircle2, CircleX, HelpCircle, Play, Plus, type LucideIcon } from "lucide-react";

import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { Copyable } from "@/components/ui/Copyable";
import { DistBars } from "@/components/ui/DistBars";
import { ScoreCell } from "@/components/ui/ScoreCell";
import {
  getEvaluationSummary,
  getProjectEvaluations,
  getRubricReport,
  getRubricVersions,
  getRubrics,
  getTraces,
  hasAuthToken,
  resolveProject,
} from "@/lib/api";
import { getActiveEnvironment } from "@/lib/active-env";
import { ignoredFieldsNotice, safeErrorMessage } from "@/lib/safe-error";
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
    ignored?: string;
    environment?: string;
  }>;
};

type Tab = "active" | "runs";
const TABS: Tab[] = ["active", "runs"];

const SEVEN_DAYS_MS = 7 * 24 * 60 * 60 * 1000;
const EVALUATION_RUNS_LIMIT = 100;

function parseTab(value: string | undefined): Tab {
  return TABS.includes(value as Tab) ? (value as Tab) : "active";
}

function buildDistribution(scores: number[], buckets = 10): number[] {
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

function withinLast7d(run: EvaluationRun): boolean {
  const t = Date.parse(run.created_at);
  return Number.isFinite(t) && Date.now() - t <= SEVEN_DAYS_MS;
}

function fmtPct(v: number | null): string {
  if (v === null) return "Sem dados";
  return `${Math.round(v * 100)}%`;
}

function fmtCost(v: number | null): string {
  if (v === null) return "Sem dados";
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(v);
}

function latestRunStatus(run: EvaluationRun | undefined): { label: string; kind: string; icon: LucideIcon } {
  if (!run) return { label: "Sem dados", kind: "unknown", icon: HelpCircle };
  if (run.passed === true) return { label: "Aprovado", kind: "approved", icon: CheckCircle2 };
  if (run.passed === false) return { label: "Reprovado", kind: "rejected", icon: CircleX };
  if (run.status === "error") return { label: "Erro", kind: "rejected", icon: CircleX };
  if (run.status === "completed") return { label: "Parcial", kind: "partial", icon: AlertTriangle };
  return { label: "Em andamento", kind: "waiting", icon: HelpCircle };
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
  const environment = await getActiveEnvironment(qp.environment);

  const [summary, evalsRes, rubricsRes, tracesRes] = await Promise.all([
    getEvaluationSummary(resolved.project_id, environment).catch(() => null),
    getProjectEvaluations(resolved.project_id, EVALUATION_RUNS_LIMIT, environment),
    getRubrics(resolved.project_id),
    getTraces({ projectId: resolved.project_id, limit: 20, environment }),
  ]);

  const runs = [...evalsRes.data].sort(
    (a, b) => Date.parse(b.created_at) - Date.parse(a.created_at),
  );
  const rubrics = rubricsRes.data;
  const traces = tracesRes.data;

  const rubricMap = new Map<string, Rubric>(rubrics.map((r) => [r.id, r]));

  const versionsByRubric = new Map<string, RubricVersion[]>();
  const reportsByRubric = new Map<string, Awaited<ReturnType<typeof getRubricReport>>>();
  await Promise.all(
    rubrics.map(async (r) => {
      const [versionsResult, reportResult] = await Promise.allSettled([
        getRubricVersions(r.id),
        getRubricReport(resolved.project_id, r.id, "7d", environment),
      ]);
      versionsByRubric.set(r.id, versionsResult.status === "fulfilled" ? versionsResult.value.data : []);
      if (reportResult.status === "fulfilled") reportsByRubric.set(r.id, reportResult.value);
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

  const totalRuns7d = summary?.runs_7d ?? null;
  const activeRubrics = summary?.active_rubrics ?? rubrics.length;
  const overallPassRate = summary?.pass_rate ?? null;
  const costUsd = summary?.cost_usd ?? null;

  const baseUrl = `/o/${org}/p/${project}/evaluations`;
  const tabHref = (t: string) => `${baseUrl}?tab=${t}`;
  const modalHref = (modal: string, extra: Record<string, string> = {}) => {
    const s = new URLSearchParams({ tab, modal, ...extra });
    return `${baseUrl}?${s.toString()}`;
  };

  const queryError = qp.error ? safeErrorMessage(qp.error, "Falha ao executar ação.") : null;
  const successMessage = qp.created
    ? "Execução de avaliação criada com sucesso."
    : qp.versioned || qp.published
      ? "Rubrica publicada."
      : null;
  const ignoredNotice = ignoredFieldsNotice(qp.ignored);

  const drawerRubricId = qp.modal === "drawer" || qp.modal === "publish" ? qp.rubric ?? null : null;
  let drawerRow: EvaluationRowSummary | null = null;
  if (drawerRubricId) {
    const row = evalRows.find((r) => r.rubric.id === drawerRubricId);
    if (row) {
      const report = reportsByRubric.get(row.rubric.id);
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
        avg_score: report?.totals.avg_score ?? null,
        runs_7d: report?.totals.runs ?? null,
        pass_rate: report?.totals.pass_rate ?? null,
        yaml_source: latest?.yaml_source ?? null,
      };
    }
  }

  return (
    <div className="page ops-page">
      <header className="ops-page-header">
        <div className="ops-page-header__copy">
          <h1 className="ops-page-header__title">Avaliações</h1>
          <p className="ops-page-header__subtitle">
            {!summary
              ? "Resumo de avaliações indisponível."
              : summary.pass_rate === null
                ? "Sem dados de taxa de aprovação nos últimos 7 dias."
                : `Nos últimos 7 dias, ${fmtPct(overallPassRate)} das execuções avaliadas passaram`}
          </p>
        </div>
        <div className="ops-page-header__actions">
          <Link href={modalHref("create")} className="btn btn--sm" aria-label="Criar nova rubrica">
            <Plus size={12} /> Nova rubrica
          </Link>
          <Link href={modalHref("run")} className="btn btn--sm btn--primary">
            <Play size={12} /> Rodar avaliação
          </Link>
        </div>
      </header>

      {queryError && (
        <div className="ops-flash ops-flash--error" role="alert">{queryError}</div>
      )}
      {successMessage && (
        <div className="ops-flash ops-flash--success" role="status">
          {successMessage}
          {ignoredNotice ? ` ${ignoredNotice}` : ""}
        </div>
      )}

      <section className="ops-metrics" aria-label="Números de 7 dias">
        <article className="ops-metric">
          <span className="ops-metric__label">Taxa de aprovação</span>
          <strong className="ops-metric__value">{fmtPct(overallPassRate)}</strong>
          <span className="ops-metric__hint">Últimos 7 dias</span>
        </article>
        <article className="ops-metric">
          <span className="ops-metric__label">Execuções avaliadas</span>
          <strong className="ops-metric__value">{totalRuns7d?.toLocaleString("pt-BR") ?? "Sem dados"}</strong>
          <span className="ops-metric__hint">Últimos 7 dias</span>
        </article>
        <article className="ops-metric">
          <span className="ops-metric__label">Rubricas ativas</span>
          <strong className="ops-metric__value">{activeRubrics.toLocaleString("pt-BR")}</strong>
          <span className="ops-metric__hint">No projeto</span>
        </article>
        <article className="ops-metric">
          <span className="ops-metric__label">Custo com o juiz</span>
          <strong className="ops-metric__value">{fmtCost(costUsd)}</strong>
          <span className="ops-metric__hint">USD · últimos 7 dias</span>
        </article>
      </section>

      <nav className="ops-tabs" aria-label="Filtros de avaliações">
        <Link href={tabHref("active")} className={`ops-tab${tab === "active" ? " is-active" : ""}`} aria-current={tab === "active" ? "page" : undefined}>
          Rubricas <span className="ops-tab__count">{evalRows.length}</span>
        </Link>
        <Link href={tabHref("runs")} className={`ops-tab${tab === "runs" ? " is-active" : ""}`} aria-current={tab === "runs" ? "page" : undefined}>
          Execuções <span className="ops-tab__count">{runs.length.toLocaleString("pt-BR")}</span>
        </Link>
      </nav>

      {tab === "active" && (
        <section className="ops-panel">
          {evalRows.length === 0 ? (
            <div className="ops-empty">
              <div className="ops-empty__title">Nenhuma rubrica cadastrada</div>
              <p className="ops-empty__description">Crie uma rubrica YAML antes de avaliar execuções.</p>
              <Link href={modalHref("create")} className="btn btn--sm btn--primary">
                <Plus size={12} /> Nova rubrica
              </Link>
            </div>
          ) : (
            <>
              <div className="ops-table-scroll">
                <table className="ops-table">
                  <thead>
                    <tr>
                      <th>Situação</th>
                      <th>Rubrica</th>
                      <th>Juiz</th>
                      <th className="ops-table__number">Execuções, 7 dias</th>
                      <th>Notas, de 0 a 1</th>
                      <th className="ops-table__number">Aprovação</th>
                      <th className="ops-table__number">Última</th>
                    </tr>
                  </thead>
                  <tbody>
                    {evalRows.map(({ rubric, runs: rubricRuns }) => {
                      const recentRuns = rubricRuns.filter(withinLast7d);
                      const scores = recentRuns
                        .filter((run) => run.passed !== null)
                        .map((run) => run.aggregate_score)
                        .filter((score): score is number => score !== null);
                      const dist = buildDistribution(scores, 10);
                      const report = reportsByRubric.get(rubric.id);
                      const lastRun = rubricRuns[0];
                      const status = latestRunStatus(lastRun);
                      const StatusIcon = status.icon;
                      const versions = versionsByRubric.get(rubric.id) ?? [];
                      const latest = versions.find((v) => v.version === rubric.current_version) ?? versions[0] ?? null;
                      const flavor = inferRubricFlavor(rubric, latest);
                      const drawerLink = modalHref("drawer", { rubric: rubric.id });
                      return (
                        <tr key={rubric.id}>
                          <td>
                            <span className={`ops-status ops-status--${status.kind}`}>
                              <StatusIcon size={14} aria-hidden="true" /> {status.label}
                            </span>
                          </td>
                          <td>
                            <Link href={drawerLink} className="ops-table__primary">
                              {rubric.slug}
                            </Link>
                            {rubric.description && <span className="ops-table__secondary">{rubric.description}</span>}
                          </td>
                          <td className="ops-mono">
                            {flavor.judge_model ?? (flavor.type_label === "Heurística" ? "Heurística" : "Sem dados")}
                          </td>
                          <td className="ops-table__number">
                            {report?.totals.runs.toLocaleString("pt-BR") ?? "Sem dados"}
                          </td>
                          <td>
                            {scores.length ? (
                              <span className="ops-distribution">
                                <DistBars dist={dist} label={`Distribuição de ${scores.length} notas carregadas`} />
                              </span>
                            ) : <span className="ops-table__muted">Sem dados</span>}
                          </td>
                          <td className="ops-table__number">{fmtPct(report?.totals.pass_rate ?? null)}</td>
                          <td className="ops-table__number ops-table__muted">
                            {lastRun ? `há ${relTime(lastRun.created_at)}` : "Sem dados"}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <p className="ops-table-note">
                Situação indica a última execução. As barras usam as avaliações recentes carregadas; os totais vêm do relatório de 7 dias.
              </p>
            </>
          )}
        </section>
      )}

      {tab === "runs" && (
        <section className="ops-panel">
          {runs.length === 0 ? (
            <div className="ops-empty">
              <div className="ops-empty__title">Nenhuma execução ainda</div>
              <p className="ops-empty__description">
                {rubrics.length === 0
                  ? "Crie uma rubrica YAML antes de rodar avaliações."
                  : traces.length === 0
                    ? "Capture um trace antes de rodar avaliações."
                    : "Escolha uma rubrica e um trace elegível para iniciar a primeira avaliação."}
              </p>
              {rubrics.length > 0 && traces.length > 0 && (
                <Link href={modalHref("run")} className="btn btn--sm btn--primary">
                  <Play size={12} /> Rodar avaliação
                </Link>
              )}
            </div>
          ) : (
            <div className="ops-table-scroll">
              <table className="ops-table">
                <thead>
                  <tr>
                    <th>Trace</th>
                    <th>Rubrica</th>
                    <th>Situação</th>
                    <th>Nota</th>
                    <th className="ops-table__number">Custo</th>
                    <th>Quando</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((run) => {
                    const rubric = rubricMap.get(run.rubric_id);
                    const traceHref = `/o/${org}/p/${project}/traces/${run.trace_id}?tab=evaluations`;
                    const status = latestRunStatus(run);
                    const StatusIcon = status.icon;
                    return (
                      <tr key={run.id}>
                        <td><Copyable value={run.trace_id} /></td>
                        <td>
                          <Link href={traceHref} className="ops-mono">
                            {rubric ? `${rubric.slug} v${run.rubric_version}` : run.rubric_id.slice(0, 12)}
                          </Link>
                        </td>
                        <td>
                          <span className={`ops-status ops-status--${status.kind}`}>
                            <StatusIcon size={14} aria-hidden="true" /> {status.label}
                          </span>
                        </td>
                        <td>{run.aggregate_score === null ? "Sem dados" : <ScoreCell value={run.aggregate_score} />}</td>
                        <td className="ops-table__number">{run.cost_usd === null ? "Sem dados" : `$${run.cost_usd.toFixed(6)}`}</td>
                        <td className="ops-table__muted">há {relTime(run.created_at)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>
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
