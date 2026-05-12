import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { createPromptAction, createPromptVersionAction } from "@/lib/actions";
import { getPromptVersions, getPrompts, hasAuthToken, resolveProject } from "@/lib/api";
import { QuickstartCard } from "@/components/QuickstartCard";

type Props = {
  params: Promise<{ org: string; project: string }>;
  searchParams: Promise<{ created?: string; versioned?: string; error?: string }>;
};

function Flash({ kind, message }: { kind: "success" | "error"; message: string }) {
  return <div className={`flash flash--${kind}`}>{message}</div>;
}

export default async function PromptsPage({ params, searchParams }: Props) {
  const { org, project } = await params;
  const qp = await searchParams;

  if (!(await hasAuthToken())) {
    return <AuthRequiredPanel layout="main" />;
  }

  const resolved = await resolveProject(org, project);
  const promptsRes = await getPrompts(resolved.project_id);
  const versionsByPrompt = new Map(
    await Promise.all(promptsRes.data.map(async (prompt) => [prompt.id, (await getPromptVersions(prompt.id)).data] as const)),
  );

  return (
    <main className="main">
      <div className="page-header">
        <div>
          <h1>Prompts</h1>
          <p className="sub">Versioned prompt registry for reproducibility and controlled experiments.</p>
        </div>
      </div>

      {qp.error ? <Flash kind="error" message={qp.error} /> : null}
      {qp.created ? <Flash kind="success" message="Prompt created." /> : null}
      {qp.versioned ? <Flash kind="success" message="Prompt version created." /> : null}

      <div className="content-grid">
        <section className="card">
          <div className="section-head">
            <div>
              <h2>Create prompt</h2>
              <p>Define slug, template and optional variables metadata.</p>
            </div>
          </div>

          <form action={createPromptAction} className="stack-form">
            <input type="hidden" name="org" value={org} />
            <input type="hidden" name="project" value={project} />
            <input type="hidden" name="project_id" value={resolved.project_id} />

            <label className="field">
              <span>Slug</span>
              <input name="slug" placeholder="support-answer-system" required />
            </label>
            <label className="field">
              <span>Description</span>
              <input name="description" placeholder="Support answer system prompt" />
            </label>
            <label className="field">
              <span>Template</span>
              <textarea
                name="template"
                className="yaml-input"
                required
                defaultValue={"You are a helpful support assistant.\nUser: {{ user_message }}"}
              />
            </label>
            <label className="field">
              <span>Variables JSON</span>
              <textarea
                name="variables_json"
                className="yaml-input"
                defaultValue={'{"user_message":{"type":"string","required":true}}'}
              />
            </label>
            <label className="field">
              <span>Metadata JSON</span>
              <textarea
                name="metadata_json"
                className="yaml-input"
                defaultValue={'{"model_default":"openai/gpt-4o-mini","temperature_default":0.2}'}
              />
            </label>
            <button type="submit" className="primary-btn">Create prompt</button>
          </form>
        </section>

        <section className="stack-list">
          {promptsRes.data.length === 0 ? (
            <div className="card">
              <QuickstartCard
                title="Nenhum prompt registrado"
                description="Versione prompts para manter experimentos e regressÃµes reproduzÃ­veis."
                steps={[
                  "Crie um prompt com slug estÃ¡vel.",
                  "Publique novas versÃµes com changelog.",
                  "Use as versÃµes em experiments/regression.",
                ]}
              />
            </div>
          ) : (
            promptsRes.data.map((prompt) => {
              const versions = versionsByPrompt.get(prompt.id) ?? [];
              const latest = versions[versions.length - 1];
              return (
                <article key={prompt.id} className="card rubric-card">
                  <div className="section-head">
                    <div>
                      <h2>{prompt.slug}</h2>
                      <p>{prompt.description ?? "No description provided."}</p>
                    </div>
                    <span className="badge badge--primary">v{prompt.current_version}</span>
                  </div>

                  <details className="details-block">
                    <summary>Versions</summary>
                    <div className="versions-stack">
                      {versions.map((version) => (
                        <div key={version.id} className="version-item">
                          <div className="version-item__head">
                            <span className="badge badge--primary">v{version.version}</span>
                            <span>{new Date(version.created_at).toLocaleString()}</span>
                          </div>
                          <pre>{version.template}</pre>
                        </div>
                      ))}
                    </div>
                  </details>

                  <details className="details-block">
                    <summary>Create version</summary>
                    <form action={createPromptVersionAction} className="stack-form">
                      <input type="hidden" name="org" value={org} />
                      <input type="hidden" name="project" value={project} />
                      <input type="hidden" name="prompt_id" value={prompt.id} />
                      <label className="field">
                        <span>Template</span>
                        <textarea
                          name="template"
                          className="yaml-input"
                          required
                          defaultValue={latest?.template ?? ""}
                        />
                      </label>
                      <label className="field">
                        <span>Variables JSON</span>
                        <textarea
                          name="variables_json"
                          className="yaml-input"
                          defaultValue={JSON.stringify(latest?.variables ?? {}, null, 2)}
                        />
                      </label>
                      <label className="field">
                        <span>Metadata JSON</span>
                        <textarea
                          name="metadata_json"
                          className="yaml-input"
                          defaultValue={JSON.stringify(latest?.metadata ?? {}, null, 2)}
                        />
                      </label>
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



