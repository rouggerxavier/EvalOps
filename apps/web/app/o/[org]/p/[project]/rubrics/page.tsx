import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { createRubricAction, createRubricVersionAction } from "@/lib/actions";
import { getRubrics, getRubricVersions, hasAuthToken, resolveProject } from "@/lib/api";
import { QuickstartCard } from "@/components/QuickstartCard";

type Props = {
  params: Promise<{ org: string; project: string }>;
  searchParams: Promise<{ created?: string; versioned?: string; error?: string }>;
};

function Flash({ kind, message }: { kind: "success" | "error"; message: string }) {
  return <div className={`flash flash--${kind}`}>{message}</div>;
}

export default async function RubricsPage({ params, searchParams }: Props) {
  const { org, project } = await params;
  const qp = await searchParams;

  if (!(await hasAuthToken())) {
    return <AuthRequiredPanel layout="main" />;
  }

  const resolved = await resolveProject(org, project);
  const rubrics = await getRubrics(resolved.project_id);
  const versionsByRubric = new Map(
    await Promise.all(
      rubrics.data.map(async (rubric) => [rubric.id, (await getRubricVersions(rubric.id)).data] as const),
    ),
  );

  return (
    <main className="main">
      <div className="page-header">
        <div>
          <h1>Rubrics</h1>
          <p className="sub">Upload YAML rubrics, review versions and keep evaluation criteria explicit.</p>
        </div>
      </div>

      {qp.error ? <Flash kind="error" message={qp.error} /> : null}
      {qp.created ? <Flash kind="success" message="Rubric created." /> : null}
      {qp.versioned ? <Flash kind="success" message="New rubric version created." /> : null}

      <div className="content-grid">
        <section className="card">
          <div className="section-head">
            <div>
              <h2>Create rubric</h2>
              <p>Paste the YAML spec used by the backend parser.</p>
            </div>
          </div>

          <form action={createRubricAction} className="stack-form">
            <input type="hidden" name="org" value={org} />
            <input type="hidden" name="project" value={project} />
            <input type="hidden" name="project_id" value={resolved.project_id} />
            <label className="field">
              <span>YAML source</span>
              <textarea
                name="yaml_source"
                className="yaml-input"
                required
                defaultValue={`slug: answer-quality\nname: Answer Quality\ndescription: Check if the answer is acceptable\nthreshold: 0.7\naggregate: weighted_mean\nevaluators:\n  - id: length_check\n    type: length_bounds\n    weight: 1.0\n    config:\n      target: trace.output.assistant_message\n      unit: chars\n      min: 20\n      max: 800`}
              />
            </label>
            <button type="submit" className="primary-btn">Create rubric</button>
          </form>
        </section>

        <section className="stack-list">
          {rubrics.data.length === 0 ? (
            <div className="card">
              <QuickstartCard
                title="Crie sua primeira rubrica"
                description="Rubricas deixam o critÃ©rio de qualidade explÃ­cito e versionado."
                steps={[
                  "Defina slug, threshold e evaluators no YAML.",
                  "Crie a rubrica com versÃ£o inicial v1.",
                  "Rode avaliaÃ§Ãµes na tela Evaluations.",
                ]}
              />
            </div>
          ) : (
            rubrics.data.map((rubric) => {
              const versions = versionsByRubric.get(rubric.id) ?? [];
              const latest = versions[versions.length - 1];
              const evaluators = latest?.parsed_spec?.evaluators ?? [];

              return (
                <article key={rubric.id} className="card rubric-card">
                  <div className="section-head">
                    <div>
                      <h2>{rubric.slug}</h2>
                      <p>{rubric.description ?? "No description provided."}</p>
                    </div>
                    <div className="meta-pills">
                      <span className="badge badge--primary">v{rubric.current_version}</span>
                      <span className="badge badge--env">threshold {rubric.threshold.toFixed(2)}</span>
                    </div>
                  </div>

                  <div className="rubric-stats">
                    <div><strong>{versions.length}</strong><span>versions</span></div>
                    <div><strong>{evaluators.length}</strong><span>evaluators</span></div>
                    <div><strong>{new Date(rubric.created_at).toLocaleDateString()}</strong><span>created</span></div>
                  </div>

                  {evaluators.length > 0 ? (
                    <div className="chip-grid">
                      {evaluators.map((evaluator) => (
                        <span key={evaluator.id} className="chip">
                          {evaluator.id} <small>{evaluator.type}</small>
                        </span>
                      ))}
                    </div>
                  ) : null}

                  <details className="details-block">
                    <summary>Versions and YAML</summary>
                    <div className="versions-stack">
                      {versions.map((version) => (
                        <div key={version.id} className="version-item">
                          <div className="version-item__head">
                            <span className="badge badge--primary">v{version.version}</span>
                            <span>{new Date(version.created_at).toLocaleString()}</span>
                          </div>
                          <pre>{version.yaml_source}</pre>
                        </div>
                      ))}
                    </div>
                  </details>

                  <details className="details-block">
                    <summary>Create new version</summary>
                    <form action={createRubricVersionAction} className="stack-form">
                      <input type="hidden" name="org" value={org} />
                      <input type="hidden" name="project" value={project} />
                      <input type="hidden" name="rubric_id" value={rubric.id} />
                      <textarea
                        name="yaml_source"
                        className="yaml-input"
                        required
                        defaultValue={latest?.yaml_source ?? ""}
                      />
                      <button type="submit" className="primary-btn">Create version</button>
                    </form>
                  </details>
                </article>
              );
            })
          )}
        </section>
      </div>
    </main>
  );
}



