import { CheckCircle2, CircleMinus } from "lucide-react";

import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { CopyTextButton } from "@/components/CopyTextButton";
import { createApiKeyAction } from "@/lib/actions";
import { getApiKeys, hasAuthToken, resolveProject } from "@/lib/api";
import { consumeApiKeyFlash } from "@/lib/flash";
import { safeErrorMessage } from "@/lib/safe-error";
import { ApiKeyActions } from "./ApiKeyActions";

type Props = {
  params: Promise<{ org: string; project: string }>;
  searchParams: Promise<{
    created?: string;
    revoked?: string;
    deleted?: string;
    error?: string;
  }>;
};

export default async function KeysPage({ params, searchParams }: Props) {
  const { org, project } = await params;
  const qp = await searchParams;

  if (!(await hasAuthToken())) return <AuthRequiredPanel layout="main" />;

  const flash = qp.created ? await consumeApiKeyFlash() : null;
  const resolved = await resolveProject(org, project);
  let keys: Awaited<ReturnType<typeof getApiKeys>>["data"] = [];
  let loadError: string | null = null;
  try {
    keys = (await getApiKeys(resolved.project_id)).data;
  } catch (error) {
    loadError = safeErrorMessage(error, "Falha ao carregar chaves de API.");
  }

  const activeCount = loadError ? null : keys.filter((key) => !key.revoked_at).length;

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1 className="page-header__title">Chaves de API</h1>
          <p className="page-header__subtitle">
            Permitem que o SDK envie traces para este projeto. Cada chave vale para um ambiente.
          </p>
        </div>
      </header>

      {qp.error ? <p className="ops-note" role="alert">{safeErrorMessage(qp.error, "Falha ao executar ação.")}</p> : null}
      {qp.created && !flash ? <p className="ops-note" role="status">Chave criada. Segredo: Sem dados. Ele só é exibido uma vez.</p> : null}
      {qp.revoked ? <p className="ops-note" role="status">Chave revogada.</p> : null}
      {qp.deleted ? <p className="ops-note" role="status">Chave excluída.</p> : null}

      {flash ? (
        <section className="card ops-key-flash" role="status">
          <div>
            <h2 className="card__title">Chave criada. Copie agora.</h2>
            <p className="card__subtitle">Este segredo não será mostrado de novo.</p>
          </div>
          <code className="mono">{flash.key}</code>
          <div className="row">
            <CopyTextButton text={flash.key} label="Copiar" copiedLabel="Copiado" />
            <span className="t__muted">Guarde esta chave em local seguro.</span>
          </div>
        </section>
      ) : null}

      <section className="card">
        <div className="card__header"><h2 className="card__title">Criar chave</h2></div>
        <form action={createApiKeyAction} className="ops-form ops-form__grid">
          <input type="hidden" name="org" value={org} />
          <input type="hidden" name="project" value={project} />
          <input type="hidden" name="project_id" value={resolved.project_id} />
          <label className="ops-form__field">
            <span>Nome</span>
            <input name="name" placeholder="production-ingest" minLength={2} required />
          </label>
          <label className="ops-form__field">
            <span>Ambiente</span>
            <select name="environment" defaultValue="prod">
              <option value="prod">Produção</option>
              <option value="staging">Staging</option>
              <option value="dev">Dev</option>
            </select>
          </label>
          <details className="ops-inline">
            <summary>Permissões avançadas</summary>
            <fieldset className="ops-form">
              <legend>Escopos</legend>
              <label><input type="checkbox" name="scopes" value="ingest" defaultChecked /> ingest</label>
              <label><input type="checkbox" name="scopes" value="read" defaultChecked /> read</label>
              <label><input type="checkbox" name="scopes" value="evaluate" /> evaluate</label>
            </fieldset>
          </details>
          <button type="submit" className="btn btn--primary">Criar chave</button>
        </form>
      </section>

      <section className="card">
        <div className="card__header">
          <h2 className="card__title">
            {activeCount === null ? "Sem dados de chaves ativas" : `${activeCount} chaves ativas`}
          </h2>
        </div>
        {loadError ? (
          <p className="ops-empty" role="alert">Não foi possível carregar chaves. {loadError}</p>
        ) : (
          <div className="table-wrap">
            <table className="t">
              <thead>
                <tr>
                  <th>Situação</th>
                  <th>Nome</th>
                  <th>Prefixo</th>
                  <th>Ambiente</th>
                  <th>Permissões</th>
                  <th>Último uso</th>
                  <th>Ações</th>
                </tr>
              </thead>
              <tbody>
                {keys.length === 0 ? (
                  <tr><td className="empty-row" colSpan={7}>Sem dados. Crie uma chave para conectar o SDK.</td></tr>
                ) : keys.map((key) => (
                  <tr key={key.id}>
                    <td>
                      {key.revoked_at ? (
                        <span className="badge"><CircleMinus size={13} aria-hidden="true" /> Revogada</span>
                      ) : (
                        <span className="badge badge--ok"><CheckCircle2 size={13} aria-hidden="true" /> Ativa</span>
                      )}
                    </td>
                    <td className="t__name">{key.name}</td>
                    <td>
                      <span className="mono">{key.prefix}</span>
                      <CopyTextButton text={key.prefix} label="Copiar prefixo" copiedLabel="Copiado" />
                    </td>
                    <td>{key.environment === "prod" ? "Produção" : key.environment === "staging" ? "Staging" : "Dev"}</td>
                    <td>{key.scopes.join(", ") || "Sem dados"}</td>
                    <td title="A lista de chaves não mostra o último uso">Sem dados</td>
                    <td>
                      <ApiKeyActions
                        org={org}
                        project={project}
                        projectId={resolved.project_id}
                        keyId={key.id}
                        revoked={Boolean(key.revoked_at)}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="ops-note">Último uso: Sem dados nesta lista.</p>
      </section>
    </div>
  );
}
