import Link from "next/link";

import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { triggerEvaluationAction } from "@/lib/actions";
import { getRubrics, getTraceEvaluations, getTraces, hasAuthToken, resolveProject } from "@/lib/api";
import { QuickstartCard } from "@/components/QuickstartCard";
import type { EvaluationRun, Trace } from "@/lib/types";

type Props = {
  params: Promise<{ org: string; project: string }>;
  searchParams: Promise<{ created?: string; error?: string }>;
};

function Flash({ kind, message }: { kind: "success" | "error"; message: string }) {
  return <div className={`flash flash--${kind}`}>{message}</div>;
}

function sortRuns(runs: EvaluationRun[]): EvaluationRun[] {
  return [...runs].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
}

export default async function EvaluationsPage({ params, searchParams }: Props) {
  const { org, project } = await params;
  const qp = await searchParams;

  if (!(await hasAuthToken())) {
    return <AuthRequiredPanel layout="main" />;
  }

  const resolved = await resolveProject(org, project);
  const [tracesRes, rubricsRes] = await Promise.all([
    getTraces({ projectId: resolved.project_id, limit: 20 }),
    getRubrics(resolved.project_id),
  ]);

  const traces = tracesRes.data;
  const rubrics = rubricsRes.data;
  const runs = sortRuns(
    (
      await Promise.all(
        traces.map(async (trace) => (await getTraceEvaluations(trace.id)).data),
      )
    ).flat(),
  );

  const traceMap = new Map<string, Trace>(traces.map((trace) => [trace.id, trace]));
  const rubricMap = new Map(rubrics.map((rubric) => [rubric.id, rubric]));

  return (
    <main className="main">
      <div className="page-header">
        <div>
          <h1>Evaluations</h1>
          <p className="sub">Run Phase 4 evaluations against captured traces and inspect score breakdowns.</p>
        </div>
      </div>

      {qp.error ? <Flash kind="error" message={qp.error} /> : null}
      {qp.created ? <Flash kind="success" message="Evaluation run created." /> : null}

      <div className="content-grid">
        <section className="card">
          <div className="section-head">
            <div>
              <h2>Run evaluation</h2>
              <p>Select a trace and an existing rubric from this project.</p>
            </div>
          </div>

          {traces.length === 0 || rubrics.length === 0 ? (
            <QuickstartCard
              title="PrÃ©-requisitos para avaliar"
              description="As avaliaÃ§Ãµes usam traces reais + uma rubrica YAML versionada."
              steps={[
                "Ingerir ao menos um trace em Traces.",
                "Criar uma rubrica na tela Rubrics.",
                "Voltar aqui e executar a avaliaÃ§Ã£o manual.",
              ]}
            />
          ) : (
            <form action={triggerEvaluationAction} className="stack-form">
              <input type="hidden" name="org" value={org} />
              <input type="hidden" name="project" value={project} />

              <label className="field">
                <span>Trace</span>
                <select name="trace_id" defaultValue={traces[0]?.id}>
                  {traces.map((trace) => (
                    <option key={trace.id} value={trace.id}>
                      {trace.name} ({trace.environment})
                    </option>
                  ))}
                </select>
              </label>

              <label className="field">
                <span>Rubric</span>
                <select name="rubric_id" defaultValue={rubrics[0]?.id}>
                  {rubrics.map((rubric) => (
                    <option key={rubric.id} value={rubric.id}>
                      {rubric.slug} (v{rubric.current_version})
                    </option>
                  ))}
                </select>
              </label>

              <label className="field">
                <span>Rubric version (optional)</span>
                <input name="rubric_version" type="number" min={1} placeholder="Leave blank for current version" />
              </label>

              <button type="submit" className="primary-btn">Run evaluation</button>
            </form>
          )}
        </section>

        <section className="card">
          <div className="section-head">
            <div>
              <h2>Recent runs</h2>
              <p>{runs.length} evaluation run(s) found across the latest traces.</p>
            </div>
          </div>

          {runs.length === 0 ? (
            <p className="empty-state">Nenhuma run ainda. Execute a primeira avaliaÃ§Ã£o acima.</p>
          ) : (
            <table className="t-table">
              <thead>
                <tr>
                  <th>Trace</th>
                  <th>Rubric</th>
                  <th>Status</th>
                  <th>Score</th>
                  <th>Cost</th>
                  <th>Evaluators</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => {
                  const trace = traceMap.get(run.trace_id);
                  const rubric = rubricMap.get(run.rubric_id);
                  return (
                    <tr key={run.id}>
                      <td>
                        {trace ? (
                          <Link href={`/o/${org}/p/${project}/traces/${trace.id}`}>{trace.name}</Link>
                        ) : (
                          <code>{run.trace_id}</code>
                        )}
                      </td>
                      <td>{rubric ? `${rubric.slug} v${run.rubric_version}` : run.rubric_id}</td>
                      <td>
                        {run.passed === true ? (
                          <span className="badge badge--passed">Passed</span>
                        ) : run.passed === false ? (
                          <span className="badge badge--failed">Failed</span>
                        ) : (
                          <span className="badge badge--review">{run.status}</span>
                        )}
                      </td>
                      <td>{run.aggregate_score !== null ? run.aggregate_score.toFixed(2) : "â€”"}</td>
                      <td>${run.cost_usd.toFixed(6)}</td>
                      <td>{run.scores.length}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </section>
      </div>

      {runs.length > 0 ? (
        <section className="card" style={{ marginTop: 18 }}>
          <div className="section-head">
            <div>
              <h2>Score breakdown</h2>
              <p>Expanded view of the latest run for each evaluation.</p>
            </div>
          </div>

          <div className="stack-list">
            {runs.slice(0, 6).map((run) => (
              <article key={run.id} className="run-card">
                <div className="run-card__head">
                  <div>
                    <strong>{rubricMap.get(run.rubric_id)?.slug ?? run.rubric_id}</strong>
                    <span> on {traceMap.get(run.trace_id)?.name ?? run.trace_id}</span>
                  </div>
                  <span className="badge badge--primary">v{run.rubric_version}</span>
                </div>
                <div className="chip-grid">
                  {run.scores.map((score) => (
                    <span key={score.id} className={`chip ${score.passed ? "chip--ok" : "chip--bad"}`}>
                      {score.evaluator_slug}: {score.score.toFixed(2)}
                    </span>
                  ))}
                </div>
              </article>
            ))}
          </div>
        </section>
      ) : null}
    </main>
  );
}



