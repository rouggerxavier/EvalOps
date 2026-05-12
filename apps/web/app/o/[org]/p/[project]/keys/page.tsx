import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { createApiKeyAction, revokeApiKeyAction } from "@/lib/actions";
import { getApiKeys, hasAuthToken, resolveProject } from "@/lib/api";
import { QuickstartCard } from "@/components/QuickstartCard";

type Props = {
  params: Promise<{ org: string; project: string }>;
  searchParams: Promise<{ created?: string; revoked?: string; key?: string; prefix?: string; error?: string }>;
};

function Flash({ kind, message }: { kind: "success" | "error"; message: string }) {
  return <div className={`flash flash--${kind}`}>{message}</div>;
}

export default async function KeysPage({ params, searchParams }: Props) {
  const { org, project } = await params;
  const qp = await searchParams;

  if (!(await hasAuthToken())) {
    return <AuthRequiredPanel layout="main" />;
  }

  const resolved = await resolveProject(org, project);
  const keys = await getApiKeys(resolved.project_id);

  return (
    <main className="main">
      <div className="page-header">
        <div>
          <h1>Chaves API</h1>
          <p className="sub">Crie chaves de ingestão, revise escopos e revogue credenciais vazadas.</p>
        </div>
      </div>

      {qp.error ? <Flash kind="error" message={qp.error} /> : null}
      {qp.created ? <Flash kind="success" message="Chave API criada. Copie o segredo agora; ele não será mostrado novamente." /> : null}
      {qp.revoked ? <Flash kind="success" message="Chave API revogada." /> : null}
      {qp.key ? (
        <section className="card secret-card">
          <div className="rail__head">
            <span className="title">Nova chave API</span>
            {qp.prefix ? <span className="badge badge--primary">{qp.prefix}</span> : null}
          </div>
          <pre className="secret-value">{qp.key}</pre>
        </section>
      ) : null}

      <div className="content-grid">
        <section className="card">
          <div className="section-head">
            <div>
              <h2>Criar chave</h2>
              <p>Use `ingest` para escrita pelo SDK e `read` para dashboards internos ou ferramentas.</p>
            </div>
          </div>

          <form action={createApiKeyAction} className="stack-form">
            <input type="hidden" name="org" value={org} />
            <input type="hidden" name="project" value={project} />
            <input type="hidden" name="project_id" value={resolved.project_id} />

            <label className="field">
              <span>Name</span>
              <input name="name" placeholder="production" required minLength={2} />
            </label>

            <label className="field">
              <span>Ambiente</span>
              <select name="environment" defaultValue="prod">
                <option value="dev">dev</option>
                <option value="staging">staging</option>
                <option value="prod">prod</option>
              </select>
            </label>

            <fieldset className="fieldset">
              <legend>Scopes</legend>
              <label className="checkbox-row">
                <input type="checkbox" name="scopes" value="ingest" defaultChecked />
                <span>ingest</span>
              </label>
              <label className="checkbox-row">
                <input type="checkbox" name="scopes" value="read" defaultChecked />
                <span>read</span>
              </label>
            </fieldset>

            <button type="submit" className="primary-btn">Criar chave</button>
          </form>
        </section>

        <section className="card">
          <div className="section-head">
            <div>
              <h2>Chaves existentes</h2>
              <p>{keys.data.length} key(s) registered for this project.</p>
            </div>
          </div>

          {keys.data.length === 0 ? (
            <QuickstartCard
              title="Nenhuma chave API ainda"
              description="Crie uma chave de ingestão antes de conectar o SDK Python."
              steps={[
                "Crie uma chave com o escopo ingest.",
                "Copie o segredo imediatamente; ele aparece uma única vez.",
                "Configure a chave no SDK Python e valide com um trace.",
              ]}
            />
          ) : (
            <table className="t-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Prefix</th>
                  <th>Env</th>
                  <th>Scopes</th>
                  <th>Status</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {keys.data.map((key) => (
                  <tr key={key.id}>
                    <td>{key.name}</td>
                    <td><code>{key.prefix}</code></td>
                    <td><span className="badge badge--env">{key.environment}</span></td>
                    <td>{key.scopes.join(", ")}</td>
                    <td>{key.revoked_at ? <span className="badge badge--failed">Revogada</span> : <span className="badge badge--passed">Ativa</span>}</td>
                    <td>
                      {!key.revoked_at ? (
                        <form action={revokeApiKeyAction}>
                          <input type="hidden" name="org" value={org} />
                          <input type="hidden" name="project" value={project} />
                          <input type="hidden" name="project_id" value={resolved.project_id} />
                          <input type="hidden" name="key_id" value={key.id} />
                          <button type="submit" className="danger-btn">Revogar</button>
                        </form>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </div>
    </main>
  );
}





