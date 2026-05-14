import Link from "next/link";
import { KeyRound, Plus, RefreshCw, ShieldCheck } from "lucide-react";

import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { CopyTextButton } from "@/components/CopyTextButton";
import { createApiKeyAction, revokeApiKeyAction } from "@/lib/actions";
import { getApiKeys, hasAuthToken, resolveProject } from "@/lib/api";
import { consumeApiKeyFlash } from "@/lib/flash";
import { formatDateTime } from "@/lib/format";

type Props = {
  params: Promise<{ org: string; project: string }>;
  searchParams: Promise<{
    tab?: string;
    created?: string;
    revoked?: string;
    error?: string;
  }>;
};

const INPUT_STYLE: React.CSSProperties = {
  width: "100%",
  background: "var(--bg-2)",
  border: "1px solid var(--border)",
  borderRadius: 6,
  padding: "7px 10px",
  color: "var(--text)",
  fontSize: 13,
};

const LABEL_STYLE: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 4,
  fontSize: 13,
};

function alertStyle(kind: "ok" | "err"): React.CSSProperties {
  if (kind === "ok") {
    return {
      padding: "10px 14px",
      background: "var(--ok-bg)",
      border: "1px solid var(--ok-border)",
      borderRadius: 6,
      color: "var(--ok)",
      fontSize: 13,
      marginBottom: 12,
    };
  }
  return {
    padding: "10px 14px",
    background: "var(--err-bg)",
    border: "1px solid var(--err-border)",
    borderRadius: 6,
    color: "var(--err)",
    fontSize: 13,
    marginBottom: 12,
  };
}

const KEY_SECRET_WARNING_STYLE: React.CSSProperties = {
  padding: "12px 14px",
  background: "rgba(245, 158, 11, 0.14)",
  border: "1px solid rgba(245, 158, 11, 0.5)",
  borderRadius: 8,
  color: "#fcd34d",
  fontSize: 13,
  lineHeight: 1.45,
};

function statusBadge(revokedAt: string | null) {
  if (revokedAt) {
    return (
      <span className="evo-badge evo-badge--err">
        <span className="evo-badge__dot" />
        revogada
      </span>
    );
  }
  return (
    <span className="evo-badge evo-badge--ok">
      <span className="evo-badge__dot" />
      ativa
    </span>
  );
}

function maskPrefix(prefix: string): string {
  return `${prefix}********`;
}

function queryString(values: Record<string, string | undefined>): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) {
    if (value) query.set(key, value);
  }
  const asString = query.toString();
  return asString ? `?${asString}` : "";
}

export default async function KeysPage({ params, searchParams }: Props) {
  const { org, project } = await params;
  const qp = await searchParams;

  if (!(await hasAuthToken())) {
    return <AuthRequiredPanel layout="main" />;
  }

  const basePath = `/o/${org}/p/${project}/keys`;
  const tab = qp.tab ?? "all";
  const flash = qp.created ? await consumeApiKeyFlash() : null;

  const resolved = await resolveProject(org, project);
  let keys: Awaited<ReturnType<typeof getApiKeys>>["data"] = [];
  let loadError: string | null = null;

  try {
    const response = await getApiKeys(resolved.project_id);
    keys = response.data;
  } catch (error) {
    loadError = error instanceof Error ? error.message : "Falha ao carregar chaves API.";
  }

  if (loadError) {
    return (
      <div className="evo-page">
        <div className="evo-page-header">
          <div>
            <h1 className="evo-page-header__title">Chaves API</h1>
            <p className="evo-page-header__subtitle">Gerencie credenciais para SDKs e integracoes.</p>
          </div>
          <div className="evo-page-header__actions">
            <Link href={basePath} className="evo-btn evo-btn--sm">
              <RefreshCw size={13} />
              Tentar novamente
            </Link>
          </div>
        </div>
        <div style={alertStyle("err")}>Nao foi possivel carregar chaves. Detalhe: {loadError}</div>
      </div>
    );
  }

  const activeCount = keys.filter((key) => !key.revoked_at).length;
  const revokedCount = keys.length - activeCount;
  const filteredKeys = keys.filter((key) => {
    if (tab === "active") return !key.revoked_at;
    if (tab === "revoked") return Boolean(key.revoked_at);
    return true;
  });

  const tabHref = (nextTab: string) =>
    `${basePath}${queryString({ tab: nextTab === "all" ? undefined : nextTab })}`;

  return (
    <div className="evo-page">
      <div className="evo-page-header">
        <div>
          <h1 className="evo-page-header__title">Chaves API</h1>
          <p className="evo-page-header__subtitle">
            Credenciais para conectar SDKs e integracoes com seguranca.
          </p>
        </div>
        <div className="evo-page-header__actions">
          <Link href="/docs" className="evo-btn evo-btn--sm">
            <ShieldCheck size={13} />
            Docs SDK
          </Link>
          <Link href="#create-key" className="evo-btn evo-btn--sm evo-btn--primary">
            <Plus size={13} />
            Nova key
          </Link>
        </div>
      </div>

      {qp.error && <div style={alertStyle("err")}>{qp.error}</div>}
      {qp.created && (
        <div style={alertStyle("ok")}>Chave API criada. Copie o segredo agora, ele nao sera exibido novamente.</div>
      )}
      {qp.revoked && <div style={alertStyle("ok")}>Chave API revogada com sucesso.</div>}

      {flash && (
        <section className="evo-card" style={{ marginBottom: 12 }}>
          <div className="evo-card__header">
            <div>
              <h3 className="evo-card__title">Nova chave criada</h3>
              <div className="evo-card__subtitle">Segredo exibido apenas nesta resposta de criacao.</div>
            </div>
            <span className="evo-badge evo-badge--info"><span className="evo-badge__dot" />{flash.prefix}</span>
          </div>
          <div className="evo-card__body" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div style={KEY_SECRET_WARNING_STYLE}>
              <strong style={{ color: "#fde68a" }}>Atenção:</strong> guarde esta chave agora. Por segurança, o segredo
              completo não pode ser recuperado depois.
            </div>
            <pre
              style={{
                margin: 0,
                background: "var(--bg-2)",
                border: "1px solid var(--border-subtle)",
                borderRadius: 8,
                padding: "10px 12px",
                fontFamily: "var(--font-mono)",
                fontSize: 12,
                color: "var(--text)",
                overflowX: "auto",
              }}
            >
              {flash.key}
            </pre>
            <div className="evo-row">
              <CopyTextButton text={flash.key} label="Copiar segredo" copiedLabel="Segredo copiado" />
              <span className="evo-faint" style={{ fontSize: 12 }}>
                Nao compartilhe este valor em logs, tickets ou commits.
              </span>
            </div>
          </div>
        </section>
      )}

      <section className="evo-kpi-grid" style={{ marginBottom: 16 }}>
        <div className="evo-metric" style={{ minHeight: 112 }}>
          <div className="evo-metric__label">
            <KeyRound size={12} />
            Chaves
          </div>
          <div className="evo-metric__value">{keys.length.toLocaleString("pt-BR")}</div>
          <div className="evo-metric__delta evo-metric__delta--neutral">total no projeto</div>
        </div>
        <div className="evo-metric" style={{ minHeight: 112 }}>
          <div className="evo-metric__label">Ativas</div>
          <div className="evo-metric__value">{activeCount.toLocaleString("pt-BR")}</div>
          <div className="evo-metric__delta evo-metric__delta--neutral">uso permitido</div>
        </div>
        <div className="evo-metric" style={{ minHeight: 112 }}>
          <div className="evo-metric__label">Revogadas</div>
          <div className="evo-metric__value">{revokedCount.toLocaleString("pt-BR")}</div>
          <div className="evo-metric__delta evo-metric__delta--neutral">sem acesso</div>
        </div>
        <div className="evo-metric" style={{ minHeight: 112 }}>
          <div className="evo-metric__label">Scopes</div>
          <div className="evo-metric__value">
            {Array.from(new Set(keys.flatMap((key) => key.scopes))).length.toLocaleString("pt-BR")}
          </div>
          <div className="evo-metric__delta evo-metric__delta--neutral">tipos de permissao</div>
        </div>
      </section>

      <nav className="evo-tabs">
        <Link href={tabHref("all")} className={`evo-tab${tab === "all" ? " is-active" : ""}`}>
          Todas
          <span className="evo-tab__count">{keys.length}</span>
        </Link>
        <Link href={tabHref("active")} className={`evo-tab${tab === "active" ? " is-active" : ""}`}>
          Ativas
          <span className="evo-tab__count">{activeCount}</span>
        </Link>
        <Link href={tabHref("revoked")} className={`evo-tab${tab === "revoked" ? " is-active" : ""}`}>
          Revogadas
          <span className="evo-tab__count">{revokedCount}</span>
        </Link>
      </nav>

      <div className="evo-grid-2col">
        <section className="evo-card" style={{ minWidth: 0 }}>
          <div className="evo-card__header">
            <h3 className="evo-card__title">Keys do projeto</h3>
            <Link href={basePath + queryString({ tab: tab === "all" ? undefined : tab })} className="evo-btn evo-btn--sm">
              <RefreshCw size={13} />
              Atualizar
            </Link>
          </div>

          <div className="evo-card__body evo-card__body--flush">
            <div style={{ overflowX: "auto" }}>
              <table className="evo-table">
                <thead>
                  <tr>
                    <th>Nome</th>
                    <th>Chave</th>
                    <th>Ambiente</th>
                    <th>Scopes</th>
                    <th>Status</th>
                    <th>Criada em</th>
                    <th>Ultimo uso</th>
                    <th style={{ width: 130 }} />
                  </tr>
                </thead>
                <tbody>
                  {filteredKeys.length === 0 ? (
                    <tr>
                      <td className="evo-empty-row" colSpan={8}>
                        Nenhuma chave encontrada para este filtro.
                      </td>
                    </tr>
                  ) : (
                    filteredKeys.map((key) => (
                      <tr key={key.id} style={key.revoked_at ? { opacity: 0.68 } : undefined}>
                        <td>
                          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                            <span className="evo-table__name">{key.name}</span>
                            <span style={{ fontSize: 11, color: "var(--text-faint)", fontFamily: "var(--font-mono)" }}>
                              {key.id}
                            </span>
                          </div>
                        </td>
                        <td>
                          <div className="evo-row" style={{ gap: 6 }}>
                            <span className="evo-mono evo-muted" style={{ fontSize: 12 }}>{maskPrefix(key.prefix)}</span>
                            <CopyTextButton
                              text={key.prefix}
                              label="Prefixo"
                              copiedLabel="Copiado"
                              className="evo-btn evo-btn--ghost evo-btn--sm"
                            />
                          </div>
                        </td>
                        <td><span className="evo-tag">{key.environment}</span></td>
                        <td>
                          <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                            {key.scopes.map((scope) => (
                              <span key={`${key.id}-${scope}`} className="evo-tag">{scope}</span>
                            ))}
                          </div>
                        </td>
                        <td>{statusBadge(key.revoked_at)}</td>
                        <td className="evo-muted" style={{ fontSize: 12 }}>{formatDateTime(key.created_at)}</td>
                        <td className="evo-muted" style={{ fontSize: 12 }}>nao disponivel</td>
                        <td>
                          {!key.revoked_at ? (
                            <form action={revokeApiKeyAction} style={{ display: "flex", justifyContent: "flex-end" }}>
                              <input type="hidden" name="org" value={org} />
                              <input type="hidden" name="project" value={project} />
                              <input type="hidden" name="project_id" value={resolved.project_id} />
                              <input type="hidden" name="key_id" value={key.id} />
                              <button type="submit" className="evo-btn evo-btn--sm">Revogar</button>
                            </form>
                          ) : (
                            <span className="evo-faint" style={{ fontSize: 12 }}>-</span>
                          )}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {keys.length === 0 && (
            <div className="evo-card__body" style={{ borderTop: "1px solid var(--border-subtle)" }}>
              <p style={{ marginTop: 0, marginBottom: 8, color: "var(--text)", fontWeight: 600 }}>
                API Keys conectam SDKs e integracoes ao EvalOps.
              </p>
              <p style={{ margin: 0, color: "var(--text-muted)", fontSize: 13 }}>
                Crie uma chave com escopo `ingest` para enviar traces e validar o fluxo ponta a ponta.
              </p>
            </div>
          )}
        </section>

        <section id="create-key" className="evo-card">
          <div className="evo-card__header">
            <h3 className="evo-card__title">Criar chave</h3>
            <span className="evo-faint" style={{ fontSize: 11 }}>acao real</span>
          </div>
          <div className="evo-card__body">
            <div style={{ ...KEY_SECRET_WARNING_STYLE, marginBottom: 12 }}>
              <strong style={{ color: "#fde68a" }}>Importante:</strong> após criar, o segredo completo aparece só uma
              vez. Salve a chave em local seguro antes de sair desta tela.
            </div>
            <form action={createApiKeyAction} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <input type="hidden" name="org" value={org} />
              <input type="hidden" name="project" value={project} />
              <input type="hidden" name="project_id" value={resolved.project_id} />

              <label style={LABEL_STYLE}>
                <span style={{ color: "var(--text-muted)" }}>Nome</span>
                <input name="name" placeholder="production-ingest" required minLength={2} style={INPUT_STYLE} />
              </label>

              <label style={LABEL_STYLE}>
                <span style={{ color: "var(--text-muted)" }}>Ambiente</span>
                <select name="environment" defaultValue="prod" style={INPUT_STYLE}>
                  <option value="dev">dev</option>
                  <option value="staging">staging</option>
                  <option value="prod">prod</option>
                </select>
              </label>

              <fieldset
                style={{
                  border: "1px solid var(--border-subtle)",
                  borderRadius: 8,
                  padding: "10px 12px",
                  display: "flex",
                  flexDirection: "column",
                  gap: 8,
                }}
              >
                <legend style={{ padding: "0 6px", color: "var(--text-muted)", fontSize: 12 }}>
                  Scopes
                </legend>
                <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "var(--text-dim)" }}>
                  <input type="checkbox" name="scopes" value="ingest" defaultChecked style={{ accentColor: "var(--accent)" }} />
                  ingest
                </label>
                <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "var(--text-dim)" }}>
                  <input type="checkbox" name="scopes" value="read" defaultChecked style={{ accentColor: "var(--accent)" }} />
                  read
                </label>
              </fieldset>

              <button type="submit" className="evo-btn evo-btn--primary" style={{ alignSelf: "flex-start" }}>
                <Plus size={13} />
                Criar chave
              </button>
            </form>
          </div>
        </section>
      </div>
    </div>
  );
}


