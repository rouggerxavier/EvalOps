import Link from "next/link";
import type { ReactNode } from "react";
import { CheckCircle2, Coins, FileCode2, History, List, MoreHorizontal, Play, Plus, Target } from "lucide-react";

import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { DistBars } from "@/components/DistBars";
import { RubricDrawer } from "@/components/RubricDrawer";
import { triggerEvaluationAction } from "@/lib/actions";
import { getProjectEvaluations, getRubricVersions, getRubrics, getTraces, hasAuthToken, resolveProject } from "@/lib/api";
import { safeErrorMessage } from "@/lib/safe-error";
import type { EvaluationRun, Rubric, RubricVersion } from "@/lib/types";

type Props = {
  params: Promise<{ org: string; project: string }>;
  searchParams: Promise<{ tab?: string; rubric?: string; created?: string; error?: string }>;
};

function buildDistribution(scores: number[], buckets = 6): number[] {
  const dist = Array<number>(buckets).fill(0);
  for (const s of scores) {
    const idx = Math.min(buckets - 1, Math.floor(s * buckets));
    dist[idx]++;
  }
  return dist;
}

const SEVEN_DAYS_MS = 7 * 24 * 60 * 60 * 1000;
const EVALUATION_RUNS_LIMIT = 100;

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
  if (v === null) return "var(--text-faint)";
  if (v >= 0.85) return "var(--ok)";
  if (v >= 0.7) return "var(--warn)";
  return "var(--err)";
}

function isWithinLast7d(run: EvaluationRun): boolean {
  const timestamp = Date.parse(run.created_at);
  return Number.isFinite(timestamp) && Date.now() - timestamp <= SEVEN_DAYS_MS;
}

function passRate(runs: EvaluationRun[]): number | null {
  const resolved = runs.filter((run) => run.passed !== null);
  if (resolved.length === 0) return null;
  return resolved.filter((run) => run.passed === true).length / resolved.length;
}

function formatPassRate(value: number | null): string {
  if (value === null) return "—";
  return `${Math.round(value * 100)}%`;
}

function formatCost(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: value > 0 && value < 0.01 ? 4 : 2,
    maximumFractionDigits: value > 0 && value < 0.01 ? 4 : 2,
  }).format(value);
}

function isHeuristic(rubric: Rubric): boolean {
  return rubric.slug.includes("heuristic") || (rubric.description ?? "").toLowerCase().includes("heurística");
}

function EvaluationSummaryCard({
  hint,
  icon,
  label,
  value,
}: {
  hint: string;
  icon: ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="evo-metric evo-evaluation-metric">
      <span className="evo-metric__label">
        {icon}
        {label}
      </span>
      <strong className="evo-metric__value">{value}</strong>
      <span className="evo-metric__delta evo-metric__delta--neutral">{hint}</span>
    </div>
  );
}

export default async function EvaluationsPage({ params, searchParams }: Props) {
  const { org, project } = await params;
  const qp = await searchParams;
  const tab = qp.tab ?? "active";

  if (!(await hasAuthToken())) {
    return <AuthRequiredPanel layout="main" />;
  }

  const resolved = await resolveProject(org, project);
  const [evalsRes, rubricsRes, tracesRes] = await Promise.all([
    getProjectEvaluations(resolved.project_id, EVALUATION_RUNS_LIMIT),
    getRubrics(resolved.project_id),
    getTraces({ projectId: resolved.project_id, limit: 20 }),
  ]);

  const runs = [...evalsRes.data].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
  const rubrics = rubricsRes.data;
  const traces = tracesRes.data;
  const safeQueryError = qp.error ? safeErrorMessage(qp.error, "Falha ao criar avaliação.") : null;

  const rubricMap = new Map<string, Rubric>(rubrics.map((r) => [r.id, r]));
  const selectedRubric = qp.rubric ? (rubricMap.get(qp.rubric) ?? null) : null;
  let selectedRubricVersions: RubricVersion[] = [];
  if (selectedRubric) {
    selectedRubricVersions = (await getRubricVersions(selectedRubric.id)).data;
  }

  const byRubric = new Map<string, { rubric: Rubric; runs: EvaluationRun[] }>();
  for (const run of runs) {
    const rubric = rubricMap.get(run.rubric_id);
    if (!rubric) continue;
    if (!byRubric.has(run.rubric_id)) byRubric.set(run.rubric_id, { rubric, runs: [] });
    byRubric.get(run.rubric_id)!.runs.push(run);
  }
  const evalRows = rubrics.map((rubric) => byRubric.get(rubric.id) ?? { rubric, runs: [] });

  const runs7d = runs.filter(isWithinLast7d).length;
  const overallPassRate = passRate(runs);
  const costUsd = runs.reduce((sum, run) => sum + run.cost_usd, 0);
  const loadedRunsHint =
    runs.length >= EVALUATION_RUNS_LIMIT
      ? `Fonte: ultimas ${EVALUATION_RUNS_LIMIT} runs carregadas`
      : "Fonte: runs carregadas";
  const baseUrl = `/o/${org}/p/${project}/evaluations`;
  const tabHref = (t: string) => `${baseUrl}?tab=${t}`;
  const rubricDrawerHref = (rubricId: string) => `${baseUrl}?tab=active&rubric=${rubricId}`;

  return (
    <div className="evo-page">
      {/* Header */}
      <div className="evo-page-header">
        <div>
          <p className="evo-page-header__eyebrow">Qualidade · Avaliações</p>
          <h1 className="evo-page-header__title">Avaliações</h1>
          <p className="evo-page-header__subtitle">
            LLM-as-judge e heurísticas executadas sobre traces de produção · {rubrics.length.toLocaleString("pt-BR")} rubrica(s) / {runs.length.toLocaleString("pt-BR")} run(s) carregadas.
          </p>
        </div>
        <div className="evo-page-header__actions">
          {traces.length > 0 && rubrics.length > 0 && (
            <Link href="#run-evaluation" className="evo-btn evo-btn--sm">
              <Play size={13} /> Rodar agora
            </Link>
          )}
          <Link
            href={`/o/${org}/p/${project}/rubrics`}
            className="evo-btn evo-btn--sm"
            data-testid="evaluations-rubrics-link"
          >
            <List size={13} /> Ver rubricas
          </Link>
          <Link href={`/o/${org}/p/${project}/rubrics`} className="evo-btn evo-btn--sm evo-btn--primary">
            <Plus size={13} /> {rubrics.length === 0 ? "Criar rubrica" : "Nova rubrica"}
          </Link>
        </div>
      </div>

      {/* Flash */}
      {safeQueryError && (
        <div style={{ padding: "10px 14px", background: "var(--err-bg)", border: "1px solid var(--err-border)", borderRadius: 6, color: "var(--err)", fontSize: 13, marginBottom: 12 }}>
          {safeQueryError}
        </div>
      )}
      {qp.created && (
        <div style={{ padding: "10px 14px", background: "var(--ok-bg)", border: "1px solid var(--ok-border)", borderRadius: 6, color: "var(--ok)", fontSize: 13, marginBottom: 12 }}>
          Run de avaliação criada com sucesso.
        </div>
      )}

      <section className="evo-kpi-grid evo-evaluations-summary" aria-label="Resumo de avaliacoes">
        <EvaluationSummaryCard
          icon={<Target size={13} />}
          label="Rubricas ativas"
          value={rubrics.length.toLocaleString("pt-BR")}
          hint="Fonte: getRubrics"
        />
        <EvaluationSummaryCard
          icon={<History size={13} />}
          label="Runs 7d"
          value={runs7d.toLocaleString("pt-BR")}
          hint={`${loadedRunsHint}; filtro created_at`}
        />
        <EvaluationSummaryCard
          icon={<CheckCircle2 size={13} />}
          label="Pass rate"
          value={formatPassRate(overallPassRate)}
          hint={overallPassRate === null ? "Sem runs concluidas nas runs carregadas" : `${loadedRunsHint}; campo passed`}
        />
        <EvaluationSummaryCard
          icon={<Coins size={13} />}
          label="Custo carregado"
          value={formatCost(costUsd)}
          hint={`${loadedRunsHint}; campo cost_usd`}
        />
      </section>

      {/* Tabs */}
      <nav className="evo-tabs">
        <Link href={tabHref("active")} className={`evo-tab${tab === "active" ? " is-active" : ""}`}>
          <Target size={13} /> Ativas
          <span className="evo-tab__count">{evalRows.length}</span>
        </Link>
        <Link href={tabHref("runs")} className={`evo-tab${tab === "runs" ? " is-active" : ""}`}>
          <History size={13} /> Runs
          <span className="evo-tab__count">{runs.length.toLocaleString("pt-BR")}</span>
        </Link>
        <Link href={tabHref("paused")} className={`evo-tab${tab === "paused" ? " is-active" : ""}`}>
          Pausadas
          <span className="evo-tab__count">0</span>
        </Link>
      </nav>

      <div className={selectedRubric ? "evo-evaluations-layout" : undefined}>
        <div>
      {/* Table: Ativas */}
      {tab === "active" && (
        <div className="evo-table-wrap">
          {evalRows.length === 0 ? (
            <div className="evo-evaluations-empty">
              <p style={{ color: "var(--text-muted)", marginBottom: 8, fontWeight: 600 }}>Nenhuma rubrica cadastrada</p>
              <p style={{ color: "var(--text-faint)", fontSize: 13 }}>
                Crie uma rubrica YAML antes de rodar avaliações sobre traces.
              </p>
              <Link href={`/o/${org}/p/${project}/rubrics`} className="evo-btn evo-btn--sm evo-btn--primary">
                <Plus size={13} /> Criar rubrica
              </Link>
            </div>
          ) : (
            <table className="evo-table">
              <thead>
                <tr>
                  <th>Evaluation</th>
                  <th>Rubric</th>
                  <th>Tipo</th>
                  <th className="evo-table__sortable">Runs (7d)</th>
                  <th className="evo-table__sortable">Pass rate</th>
                  <th className="evo-table__sortable">Score médio</th>
                  <th>Distribuição</th>
                  <th className="evo-table__sortable">Atualizada</th>
                  <th style={{ width: 72 }} />
                </tr>
              </thead>
              <tbody>
                {evalRows.map(({ rubric, runs: rubricRuns }) => {
                  const scores = rubricRuns.map((r) => r.aggregate_score).filter((s): s is number => s !== null);
                  const avg = scores.length > 0 ? scores.reduce((a, b) => a + b, 0) / scores.length : null;
                  const dist = buildDistribution(scores);
                  const lastRun = rubricRuns[0];
                  const heuristic = isHeuristic(rubric);
                  const rubricRuns7d = rubricRuns.filter(isWithinLast7d).length;
                  const rubricPassRate = passRate(rubricRuns);
                  return (
                    <tr key={rubric.id}>
                      <td>
                        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                          <span className="evo-table__name">{rubric.slug}</span>
                          <span style={{ fontSize: 11, color: "var(--text-faint)", fontFamily: "var(--font-mono)" }}>
                            eval_{rubric.slug}
                          </span>
                        </div>
                      </td>
                      <td>
                        <span className="evo-mono evo-muted" style={{ fontSize: 12 }}>
                          {rubric.slug}_v{rubric.current_version}
                        </span>
                      </td>
                      <td>
                        <span className={`evo-badge ${heuristic ? "evo-badge--info" : "evo-badge--eval"}`}>
                          <span className="evo-badge__dot" />
                          {heuristic ? "Heurística" : "LLM-as-judge"}
                        </span>
                      </td>
                      <td className="evo-table__num">{rubricRuns7d.toLocaleString("pt-BR")}</td>
                      <td>
                        <span className="evo-mono evo-muted" style={{ fontSize: 12 }}>
                          {formatPassRate(rubricPassRate)}
                        </span>
                      </td>
                      <td>
                        {avg === null ? (
                          <span className="evo-faint">—</span>
                        ) : (
                          <span style={{ fontFamily: "var(--font-mono)", fontSize: 13, color: scoreColor(avg) }}>
                            {avg.toFixed(2)}
                          </span>
                        )}
                      </td>
                      <td>
                        {scores.length > 0 ? <DistBars dist={dist} /> : <span className="evo-faint">—</span>}
                      </td>
                      <td className="evo-muted">{lastRun ? relTime(lastRun.created_at) + " atrás" : "—"}</td>
                      <td>
                        <div className="evo-row">
                          <Link
                            href={rubricDrawerHref(rubric.id)}
                            className="evo-btn evo-btn--ghost evo-btn--sm evo-btn--icon"
                            title="Ver YAML da rubrica"
                            aria-label={`Ver YAML de ${rubric.slug}`}
                          >
                            <FileCode2 size={14} />
                          </Link>
                          <button
                            type="button"
                            className="evo-btn evo-btn--ghost evo-btn--sm evo-btn--icon"
                            disabled
                            data-status="planned"
                            title="Ações por avaliação — em breve"
                          >
                            <MoreHorizontal size={14} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* Table: Runs */}
      {tab === "runs" && (
        <div className="evo-table-wrap">
          {runs.length === 0 ? (
            <div className="evo-evaluations-empty">
              <p style={{ color: "var(--text-muted)", marginBottom: 8, fontWeight: 600 }}>Nenhuma run ainda</p>
              <p style={{ color: "var(--text-faint)", fontSize: 13 }}>
                {rubrics.length === 0
                  ? "Crie uma rubrica YAML antes de rodar avaliações."
                  : traces.length === 0
                    ? "Capture um trace antes de rodar avaliações."
                    : "Use uma rubrica versionada e um trace elegível para iniciar a primeira run."}
              </p>
              <div className="evo-row" style={{ justifyContent: "center", marginTop: 14 }}>
                {rubrics.length === 0 ? (
                  <Link href={`/o/${org}/p/${project}/rubrics`} className="evo-btn evo-btn--sm evo-btn--primary">
                    <Plus size={13} /> Criar rubrica
                  </Link>
                ) : traces.length === 0 ? (
                  <Link href={`/o/${org}/p/${project}/traces`} className="evo-btn evo-btn--sm">
                    Ver traces
                  </Link>
                ) : (
                  <Link href={tabHref("active")} className="evo-btn evo-btn--sm">
                    <Play size={13} /> Rodar agora
                  </Link>
                )}
              </div>
            </div>
          ) : (
            <table className="evo-table">
              <thead>
                <tr>
                  <th>Trace</th>
                  <th>Rubric</th>
                  <th>Status</th>
                  <th className="evo-table__sortable">Score</th>
                  <th className="evo-table__sortable">Custo</th>
                  <th className="evo-table__sortable">Quando</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => {
                  const rubric = rubricMap.get(run.rubric_id);
                  return (
                    <tr key={run.id}>
                      <td>
                        <Link
                          href={`/o/${org}/p/${project}/traces/${run.trace_id}`}
                          style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--accent)" }}
                        >
                          {run.trace_id.slice(0, 12)}…
                        </Link>
                      </td>
                      <td>
                        <span className="evo-mono evo-muted" style={{ fontSize: 12 }}>
                          {rubric ? `${rubric.slug} v${run.rubric_version}` : run.rubric_id.slice(0, 12)}
                        </span>
                      </td>
                      <td>
                        {run.passed === true ? (
                          <span className="evo-badge evo-badge--ok"><span className="evo-badge__dot" />Passou</span>
                        ) : run.passed === false ? (
                          <span className="evo-badge evo-badge--err"><span className="evo-badge__dot" />Falhou</span>
                        ) : (
                          <span className="evo-badge"><span className="evo-badge__dot" />{run.status}</span>
                        )}
                      </td>
                      <td>
                        {run.aggregate_score === null ? (
                          <span className="evo-faint">—</span>
                        ) : (
                          <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: scoreColor(run.aggregate_score) }}>
                            {run.aggregate_score.toFixed(2)}
                          </span>
                        )}
                      </td>
                      <td className="evo-table__num evo-muted" style={{ fontSize: 12 }}>
                        ${run.cost_usd.toFixed(6)}
                      </td>
                      <td className="evo-muted" style={{ fontSize: 12 }}>{relTime(run.created_at)} atrás</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* Paused */}
      {tab === "paused" && (
        <div className="evo-table-wrap">
          <div style={{ padding: "40px 24px", textAlign: "center" }}>
            <p style={{ color: "var(--text-faint)", fontSize: 13 }}>Nenhuma avaliação pausada.</p>
          </div>
        </div>
      )}

      {/* Run trigger (collapsible) */}
      {tab === "active" && traces.length > 0 && rubrics.length > 0 && (
        <details
          id="run-evaluation"
          style={{
            background: "var(--surface-1)",
            border: "1px solid var(--border)",
            borderRadius: 8,
            marginTop: 16,
          }}
        >
          <summary
            style={{
              padding: "12px 16px",
              cursor: "pointer",
              fontSize: 13,
              fontWeight: 500,
              color: "var(--text-dim)",
              listStyle: "none",
            }}
          >
            Rodar nova avaliação
          </summary>
          <div style={{ padding: "0 16px 16px" }}>
            <form action={triggerEvaluationAction} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <input type="hidden" name="org" value={org} />
              <input type="hidden" name="project" value={project} />

              <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 13 }}>
                <span style={{ color: "var(--text-muted)" }}>Trace</span>
                <select name="trace_id" defaultValue={traces[0]?.id} style={{ background: "var(--bg-2)", border: "1px solid var(--border)", borderRadius: 6, padding: "6px 10px", color: "var(--text)", fontSize: 13 }}>
                  {traces.map((trace) => (
                    <option key={trace.id} value={trace.id}>
                      {trace.name} ({trace.environment})
                    </option>
                  ))}
                </select>
              </label>

              <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 13 }}>
                <span style={{ color: "var(--text-muted)" }}>Rubric</span>
                <select name="rubric_id" defaultValue={rubrics[0]?.id} style={{ background: "var(--bg-2)", border: "1px solid var(--border)", borderRadius: 6, padding: "6px 10px", color: "var(--text)", fontSize: 13 }}>
                  {rubrics.map((rubric) => (
                    <option key={rubric.id} value={rubric.id}>
                      {rubric.slug} (v{rubric.current_version})
                    </option>
                  ))}
                </select>
              </label>

              <button type="submit" className="evo-btn evo-btn--primary" style={{ alignSelf: "flex-start" }}>
                Rodar avaliação
              </button>
            </form>
          </div>
        </details>
      )}
        </div>

        {selectedRubric && (
          <RubricDrawer closeHref={tabHref(tab)} rubric={selectedRubric} versions={selectedRubricVersions} />
        )}
      </div>
    </div>
  );
}
