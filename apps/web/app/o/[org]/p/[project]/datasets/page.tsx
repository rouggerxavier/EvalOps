import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { addDatasetItemAction, buildDatasetFromTracesAction, createDatasetAction } from "@/lib/actions";
import { getDatasetItems, getDatasets, hasAuthToken, resolveProject } from "@/lib/api";
import { QuickstartCard } from "@/components/QuickstartCard";

type Props = {
  params: Promise<{ org: string; project: string }>;
  searchParams: Promise<{ created?: string; items_added?: string; built?: string; error?: string }>;
};

function Flash({ kind, message }: { kind: "success" | "error"; message: string }) {
  return <div className={`flash flash--${kind}`}>{message}</div>;
}

export default async function DatasetsPage({ params, searchParams }: Props) {
  const { org, project } = await params;
  const qp = await searchParams;

  if (!(await hasAuthToken())) {
    return <AuthRequiredPanel layout="main" />;
  }

  const resolved = await resolveProject(org, project);
  const datasetsRes = await getDatasets(resolved.project_id);
  const itemsByDataset = new Map(
    await Promise.all(datasetsRes.data.map(async (dataset) => [dataset.id, (await getDatasetItems(dataset.id)).data] as const)),
  );

  return (
    <main className="main">
      <div className="page-header">
        <div>
          <h1>Datasets</h1>
          <p className="sub">Curate trace-based or manual datasets used by experiments and regression checks.</p>
        </div>
      </div>

      {qp.error ? <Flash kind="error" message={qp.error} /> : null}
      {qp.created ? <Flash kind="success" message="Dataset created." /> : null}
      {qp.items_added ? <Flash kind="success" message="Dataset item added." /> : null}
      {qp.built ? <Flash kind="success" message="Dataset populated from traces." /> : null}

      <div className="content-grid">
        <section className="card">
          <div className="section-head">
            <div>
              <h2>Create dataset</h2>
              <p>Choose manual or traces as source.</p>
            </div>
          </div>

          <form action={createDatasetAction} className="stack-form">
            <input type="hidden" name="org" value={org} />
            <input type="hidden" name="project" value={project} />
            <input type="hidden" name="project_id" value={resolved.project_id} />

            <label className="field">
              <span>Slug</span>
              <input name="slug" placeholder="support-golden-set" required />
            </label>
            <label className="field">
              <span>Description</span>
              <input name="description" placeholder="Golden set for support traces" />
            </label>
            <label className="field">
              <span>Source</span>
              <select name="source" defaultValue="manual">
                <option value="manual">manual</option>
                <option value="traces">traces</option>
              </select>
            </label>
            <button type="submit" className="primary-btn">Create dataset</button>
          </form>
        </section>

        <section className="stack-list">
          {datasetsRes.data.length === 0 ? (
            <div className="card">
              <QuickstartCard
                title="Nenhum dataset ainda"
                description="Datasets sustentam regressÃ£o, experimentos e comparaÃ§Ã£o de variantes."
                steps={[
                  "Crie um dataset manual para baseline.",
                  "Ou faÃ§a build a partir de traces reais.",
                  "Depois rode experiments com rubricas.",
                ]}
              />
            </div>
          ) : (
            datasetsRes.data.map((dataset) => {
              const items = itemsByDataset.get(dataset.id) ?? [];
              return (
                <article key={dataset.id} className="card rubric-card">
                  <div className="section-head">
                    <div>
                      <h2>{dataset.slug}</h2>
                      <p>{dataset.description ?? "No description provided."}</p>
                    </div>
                    <div className="meta-pills">
                      <span className="badge badge--env">{dataset.source}</span>
                      <span className="badge badge--primary">{items.length} items</span>
                    </div>
                  </div>

                  <details className="details-block">
                    <summary>Add item manually</summary>
                    <form action={addDatasetItemAction} className="stack-form">
                      <input type="hidden" name="org" value={org} />
                      <input type="hidden" name="project" value={project} />
                      <input type="hidden" name="dataset_id" value={dataset.id} />
                      <label className="field">
                        <span>Input JSON</span>
                        <textarea
                          name="input_json"
                          className="yaml-input"
                          defaultValue={'{"messages":[{"role":"user","content":"How do I reset my password?"}]}'}
                        />
                      </label>
                      <label className="field">
                        <span>Expected output JSON</span>
                        <textarea
                          name="expected_output_json"
                          className="yaml-input"
                          defaultValue={'{"assistant_message":"Use the reset password link from login."}'}
                        />
                      </label>
                      <label className="field">
                        <span>Metadata JSON</span>
                        <textarea
                          name="metadata_json"
                          className="yaml-input"
                          defaultValue={"{}"}
                        />
                      </label>
                      <button type="submit" className="primary-btn">Add item</button>
                    </form>
                  </details>

                  <details className="details-block">
                    <summary>Build from traces</summary>
                    <form action={buildDatasetFromTracesAction} className="stack-form">
                      <input type="hidden" name="org" value={org} />
                      <input type="hidden" name="project" value={project} />
                      <input type="hidden" name="dataset_id" value={dataset.id} />
                      <label className="field">
                        <span>Environment</span>
                        <select name="environment" defaultValue="">
                          <option value="">any</option>
                          <option value="dev">dev</option>
                          <option value="staging">staging</option>
                          <option value="prod">prod</option>
                        </select>
                      </label>
                      <label className="field">
                        <span>Status</span>
                        <select name="status" defaultValue="">
                          <option value="">any</option>
                          <option value="ok">ok</option>
                          <option value="partial">partial</option>
                          <option value="error">error</option>
                        </select>
                      </label>
                      <label className="field">
                        <span>Limit</span>
                        <input name="limit" type="number" min={1} max={500} defaultValue={50} />
                      </label>
                      <button type="submit" className="primary-btn">Build from traces</button>
                    </form>
                  </details>

                  {items.length > 0 ? (
                    <details className="details-block">
                      <summary>Preview items</summary>
                      <div className="versions-stack">
                        {items.slice(0, 5).map((item) => (
                          <div key={item.id} className="version-item">
                            <div className="version-item__head">
                              <span className="badge badge--primary">#{item.ord}</span>
                              <span>{new Date(item.created_at).toLocaleString()}</span>
                            </div>
                            <pre>{JSON.stringify(item.input, null, 2)}</pre>
                          </div>
                        ))}
                      </div>
                    </details>
                  ) : null}
                </article>
              );
            })
          )}
        </section>
      </div>
    </main>
  );
}



