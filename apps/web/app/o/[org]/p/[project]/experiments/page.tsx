import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { createExperimentAction, runExperimentAction } from "@/lib/actions";
import { getDatasets, getExperimentRun, getExperiments, getRubrics, hasAuthToken, resolveProject } from "@/lib/api";
import { QuickstartCard } from "@/components/QuickstartCard";

type Props = {
  params: Promise<{ org: string; project: string }>;
  searchParams: Promise<{ created?: string; run?: string; run_id?: string; experiment_id?: string; error?: string }>;
};

function Flash({ kind, message }: { kind: "success" | "error"; message: string }) {
  return <div className={`flash flash--${kind}`}>{message}</div>;
}

export default async function ExperimentsPage({ params, searchParams }: Props) {
  const { org, project } = await params;
  const qp = await searchParams;

  if (!(await hasAuthToken())) {
    return <AuthRequiredPanel layout="main" />;
  }

  const resolved = await resolveProject(org, project);
  const [datasetsRes, rubricsRes, experimentsRes] = await Promise.all([
    getDatasets(resolved.project_id),
    getRubrics(resolved.project_id),
    getExperiments(resolved.project_id),
  ]);

  let runDetail: Awaited<ReturnType<typeof getExperimentRun>> | null = null;
  if (qp.run_id && qp.experiment_id) {
    try {
      runDetail = await getExperimentRun(qp.experiment_id, qp.run_id);
    } catch {
      runDetail = null;
    }
  }

  return (
    <main className="main">
      <div className="page-header">
        <div>
          <h1>Experiments</h1>
          <p className="sub">Run controlled comparisons on datasets with rubric-based pass criteria.</p>
        </div>
      </div>

      {qp.error ? <Flash kind="error" message={qp.error} /> : null}
      {qp.created ? <Flash kind="success" message="Experiment created." /> : null}
      {qp.run ? <Flash kind="success" message="Experiment run executed." /> : null}

      {runDetail?.run ? (
        <section className="card" style={{ marginBottom: 18 }}>
          <div className="section-head">
            <div>
              <h2>Latest run summary</h2>
              <p>Run ID: <code>{runDetail.run.id}</code></p>
            </div>
            <span className={`badge ${runDetail.run.passed ? "badge--passed" : "badge--failed"}`}>
              {runDetail.run.passed ? "Passed" : "Failed"}
            </span>
          </div>
          <div className="chip-grid">
            {Object.entries(runDetail.run.by_variant).map(([variant, metrics]) => (
              <span key={variant} className="chip">
                {variant}: {(metrics.pass_rate * 100).toFixed(1)}% pass rate
              </span>
            ))}
          </div>
          {runDetail.run.criteria_failures.length > 0 ? (
            <div style={{ marginTop: 10 }}>
              <strong>Criteria failures:</strong>
              <pre>{JSON.stringify(runDetail.run.criteria_failures, null, 2)}</pre>
            </div>
          ) : null}
        </section>
      ) : null}

      <div className="content-grid">
        <section className="card">
          <div className="section-head">
            <div>
              <h2>Create experiment</h2>
              <p>Choose dataset/rubric and define variants in JSON.</p>
            </div>
          </div>

          <form action={createExperimentAction} className="stack-form">
            <input type="hidden" name="org" value={org} />
            <input type="hidden" name="project" value={project} />
            <input type="hidden" name="project_id" value={resolved.project_id} />

            <label className="field">
              <span>Name</span>
              <input name="name" placeholder="q2-model-comparison" required />
            </label>

            <label className="field">
              <span>Dataset</span>
              <select name="dataset_id" defaultValue={datasetsRes.data[0]?.id ?? ""} required>
                {datasetsRes.data.map((dataset) => (
                  <option key={dataset.id} value={dataset.id}>{dataset.slug}</option>
                ))}
              </select>
            </label>

            <label className="field">
              <span>Rubric</span>
              <select name="rubric_id" defaultValue={rubricsRes.data[0]?.id ?? ""} required>
                {rubricsRes.data.map((rubric) => (
                  <option key={rubric.id} value={rubric.id}>{rubric.slug} (v{rubric.current_version})</option>
                ))}
              </select>
            </label>

            <label className="field">
              <span>Baseline variant</span>
              <input name="baseline_variant" defaultValue="control" />
            </label>

            <label className="field">
              <span>Variants JSON</span>
              <textarea
                name="variants_json"
                className="yaml-input"
                defaultValue={JSON.stringify([
                  { name: "control", model: "openai/gpt-4o-mini", params: { temperature: 0.2 } },
                  { name: "candidate", model: "openai/gpt-4.1", params: { temperature: 0.2 } },
                ], null, 2)}
              />
            </label>

            <label className="field">
              <span>Pass criteria JSON</span>
              <textarea
                name="pass_criteria_json"
                className="yaml-input"
                defaultValue={JSON.stringify(
                  { min_pass_rate: 0.7, no_regression_vs: "control", no_regression_delta: 0.02 },
                  null,
                  2,
                )}
              />
            </label>
            <button type="submit" className="primary-btn">Create experiment</button>
          </form>
        </section>

        <section className="stack-list">
          {experimentsRes.data.length === 0 ? (
            <div className="card">
              <QuickstartCard
                title="Nenhum experimento criado"
                description="Experiments comparam variantes no mesmo dataset com a mesma rubrica."
                steps={[
                  "Garanta ao menos um dataset e uma rubrica.",
                  "Crie variantes control/candidate.",
                  "Execute e acompanhe pass rate/custo.",
                ]}
              />
            </div>
          ) : (
            experimentsRes.data.map((experiment) => (
              <article key={experiment.id} className="card run-card">
                <div className="run-card__head">
                  <div>
                    <strong>{experiment.name}</strong>
                    <div className="muted" style={{ marginTop: 4 }}>
                      {experiment.variants.length} variants â€¢ dataset {experiment.dataset_id}
                    </div>
                  </div>
                  <span className="badge badge--primary">{experiment.baseline_variant ?? "no baseline"}</span>
                </div>

                <div className="chip-grid">
                  {experiment.variants.map((variant) => (
                    <span key={variant.name} className="chip">
                      {variant.name}
                      {variant.model ? <small>{variant.model}</small> : null}
                    </span>
                  ))}
                </div>

                <form action={runExperimentAction}>
                  <input type="hidden" name="org" value={org} />
                  <input type="hidden" name="project" value={project} />
                  <input type="hidden" name="experiment_id" value={experiment.id} />
                  <button type="submit" className="primary-btn">Run experiment</button>
                </form>
              </article>
            ))
          )}
        </section>
      </div>
    </main>
  );
}



