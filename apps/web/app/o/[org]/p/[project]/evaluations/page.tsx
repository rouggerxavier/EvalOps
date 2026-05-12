import Link from "next/link";
import { History, MoreHorizontal, Play, Plus, Target } from "lucide-react";

import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { triggerEvaluationAction } from "@/lib/actions";
import { getProjectEvaluations, getRubrics, getTraces, hasAuthToken, resolveProject } from "@/lib/api";
import type { EvaluationRun, Rubric } from "@/lib/types";

type Props = {
  params: Promise<{ org: string; project: string }>;
  searchParams: Promise<{ tab?: string; created?: string; error?: string }>;
};

function buildDistribution(scores: number[], buckets = 6): number[] {
  const dist = Array<number>(buckets).fill(0);
  for (const s of scores) {
    const idx = Math.min(buckets - 1, Math.floor(s * buckets));
    dist[idx]++;
  }
  return dist;
}

function DistBars({ dist }: { dist: number[] }) {
  const max = Math.max(...dist, 1);
  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: 2, height: 24 }}>
      {dist.map((v, i) => {
        const heightPx = Math.max(2, Math.round((v / max) * 22));
        const color = i < 2 ? "var(--err)" : i < 4 ? "var(--warn)" : "var(--ok)";
        return (
          <div
            key={i}
            style={{ width: 12, height: heightPx, background: color, opacity: 0.85, borderRadius: 1 }}
            title={`${v} run(s)`}
          />
        );
      })}
    </div>
  );
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
  if (v === null) return "var(--text-faint)";
  if (v >= 0.85) return "var(--ok)";
  if (v >= 0.7) return "var(--warn)";
  return "var(--err)";
}

function isHeuristic(rubric: Rubric): boolean {
  return rubric.slug.includes("heuristic") || (rubric.description ?? "").toLowerCase().includes("heurística");
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
    getProjectEvaluations(resolved.project_id),
    getRubrics(resolved.project_id),
    getTraces({ projectId: resolved.project_id, limit: 20 }),
  ]);

  const runs = evalsRes.data;
  const rubrics = rubricsRes.data;
  const traces = tracesRes.data;

  const rubricMap = new Map<string, Rubric>(rubrics.map((r) => [r.id, r]));

  const byRubric = new Map<string, { rubric: Rubric; runs: EvaluationRun[] }>();
  for (const run of runs) {
    const rubric = rubricMap.get(run.rubric_id);
    if (!rubric) continue;
    if (!byRubric.has(run.rubric_id)) byRubric.set(run.rubric_id, { rubric, runs: [] });
    byRubric.get(run.rubric_id)!.runs.push(run);
  }
  const evalRows = Array.from(byRubric.values());

  const tabHref = (t: string) => `/o/${org}/p/${project}/evaluations?tab=${t}`;

  return (
    <div className="evo-page">
      {/* Header */}
      <div className="evo-page-header">
        <div>
          <h1 className="evo-page-header__title">Evaluations</h1>
          <p className="evo-page-header__subtitle">
            Avaliações LLM-as-judge e heurísticas rodadas sobre traces de produção.
          </p>
        </div>
        <div className="evo-row">
          <button type="button" className="evo-btn evo-btn--sm">
            <Play size={13} /> Rodar agora
          </button>
          <button type="button" className="evo-btn evo-btn--sm evo-btn--primary">
            <Plus size={13} /> Nova evaluation
          </button>
        </div>
      </div>

      {/* Flash */}
      {qp.error && (
        <div style={{ padding: "10px 14px", background: "var(--err-bg)", border: "1px solid var(--err-border)", borderRadius: 6, color: "var(--err)", fontSize: 13, marginBottom: 12 }}>
          {qp.error}
        </div>
      )}
      {qp.created && (
        <div style={{ padding: "10px 14px", background: "var(--ok-bg)", border: "1px solid var(--ok-border)", borderRadius: 6, color: "var(--ok)", fontSize: 13, marginBottom: 12 }}>
          Run de avaliação criada com sucesso.
        </div>
      )}

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

      {/* Table: Ativas */}
      {tab === "active" && (
        <div className="evo-table-wrap">
          {evalRows.length === 0 ? (
            <div style={{ padding: "40px 24px", textAlign: "center" }}>
              <p style={{ color: "var(--text-muted)", marginBottom: 8, fontWeight: 600 }}>Nenhuma avaliação ainda</p>
              <p style={{ color: "var(--text-faint)", fontSize: 13 }}>
                Ingira ao menos um trace via SDK e crie uma rubrica para começar.
              </p>
            </div>
          ) : (
            <table className="evo-table">
              <thead>
                <tr>
                  <th>Evaluation</th>
                  <th>Rubric</th>
                  <th>Tipo</th>
                  <th>Judge model</th>
                  <th className="evo-table__sortable">Runs (7d)</th>
                  <th className="evo-table__sortable">Score médio</th>
                  <th>Distribuição</th>
                  <th className="evo-table__sortable">Atualizada</th>
                  <th style={{ width: 32 }} />
                </tr>
              </thead>
              <tbody>
                {evalRows.map(({ rubric, runs: rubricRuns }) => {
                  const scores = rubricRuns.map((r) => r.aggregate_score).filter((s): s is number => s !== null);
                  const avg = scores.length > 0 ? scores.reduce((a, b) => a + b, 0) / scores.length : null;
                  const dist = buildDistribution(scores);
                  const lastRun = rubricRuns[0];
                  const heuristic = isHeuristic(rubric);
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
                      <td className="evo-mono evo-muted" style={{ fontSize: 12 }}>—</td>
                      <td className="evo-table__num">{rubricRuns.length.toLocaleString("pt-BR")}</td>
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
                        <button type="button" className="evo-btn evo-btn--ghost evo-btn--sm evo-btn--icon">
                          <MoreHorizontal size={14} />
                        </button>
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
            <div style={{ padding: "40px 24px", textAlign: "center" }}>
              <p style={{ color: "var(--text-muted)", marginBottom: 8, fontWeight: 600 }}>Nenhuma run ainda</p>
              <p style={{ color: "var(--text-faint)", fontSize: 13 }}>
                Avaliações precisam de traces capturados e uma rubrica YAML versionada.
              </p>
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
  );
}
