/* =============================================================
   Secondary modules: Prompts, Rubricas, Datasets, Experimentos,
   Chaves API, Exports.
   Each renders a "preserved module" premium placeholder showing:
     - what the module does
     - real items (mocked from codebase)
     - real backend endpoints preserved
   ============================================================= */

const { useState: useStateM } = React;

function ModuleScreen({ moduleId, onNav }) {
  const m = window.MODULES[moduleId];
  const [previewAction, setPreviewAction] = useStateM(null);
  if (!m) return <div className="page"><h1>Módulo desconhecido</h1></div>;

  // module-specific column meta
  const colsByModule = {
    prompts:     ["Prompt",     "Versão atual", "Usado por",  "Atualização"],
    rubrics:     ["Rubrica",    "Versão atual", "Tipo",        "Atualização"],
    datasets:    ["Dataset",    "Tamanho",       "Em uso por", "Atualização"],
    experiments: ["Experimento","Estado",        "Dataset",    "Atualização"],
    keys:        ["Nome",       "Chave",         "Usada por",  "Último uso"],
    exports:     ["Job",        "Tamanho",       "Solicitado por","Quando"],
  };
  const cols = colsByModule[moduleId];
  const iconByModule = {
    prompts: "sparkles", rubrics: "list", datasets: "database",
    experiments: "flask", keys: "key", exports: "download",
  };

  // module-specific actions
  const primaryAction = {
    prompts:     { label: "Nova versão de prompt", endpoint: "createPrompt" },
    rubrics:     { label: "Nova rubrica",           endpoint: "createRubric" },
    datasets:    { label: "Criar dataset",          endpoint: "createDataset" },
    experiments: { label: "Criar experimento",      endpoint: "createExperiment" },
    keys:        { label: "Criar API key",          endpoint: "createKey" },
    exports:     { label: "Novo export JSONL",      endpoint: "createExport" },
  }[moduleId];

  const subtitleByModule = {
    prompts:     "Versionamento por hash. Cada trace é amarrado à versão exata do prompt usada.",
    rubrics:     "Critérios YAML versionados, executados como LLM-as-judge ou heurísticas.",
    datasets:    "Golden sets curados a partir de traces — usados em regressão e experimentos.",
    experiments: "Compara prompts ou modelos sobre um dataset. Reporta delta de qualidade, custo e latência.",
    keys:        "Chaves de ingestão usadas pelo SDK. Exibidas sempre mascaradas. O segredo cru aparece apenas na criação.",
    exports:     "Jobs de exportação JSONL. Use para fine-tune offline, auditoria ou compartilhar evidência.",
  };

  return (
    <div className="page">
      <PageHeader
        eyebrow={["keys", "exports"].includes(moduleId) ? "Operação" : "Recursos"}
        title={
          <span style={{ display: "flex", alignItems: "center", gap: 12 }}>
            {m.title}
            <PreviewPill label="módulo preservado" />
          </span>
        }
        subtitle={subtitleByModule[moduleId]}
        actions={
          <>
            {moduleId === "exports" && (
              <button className="btn btn--sm" onClick={() => setPreviewAction("downloadExport")}>
                <Icon name="download" size={12} /> Baixar último
              </button>
            )}
            <button className="btn btn--sm btn--primary" onClick={() => setPreviewAction(primaryAction.endpoint)}>
              <Icon name="plus" size={12} /> {primaryAction.label}
            </button>
          </>
        }
      />

      {/* Module banner — "preserved, out of redesign" */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "auto 1fr auto",
        gap: 12,
        alignItems: "center",
        padding: "12px 16px",
        background: "linear-gradient(135deg, var(--accent-soft), oklch(0.205 0.014 250))",
        border: "1px solid var(--accent-rim)",
        borderRadius: "var(--r-md)",
        marginBottom: 16,
      }}>
        <div style={{
          width: 32, height: 32, borderRadius: "var(--r-sm)",
          background: "var(--accent-soft)", border: "1px solid var(--accent-rim)",
          display: "grid", placeItems: "center", color: "var(--accent)",
        }}>
          <Icon name={iconByModule[moduleId]} size={14} />
        </div>
        <div>
          <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text)", marginBottom: 2 }}>
            Funcionalidade preservada — fora do redesign principal nesta primeira versão
          </div>
          <div style={{ fontSize: 11.5, color: "var(--text-muted)" }}>
            Endpoints e ações reais continuam representados abaixo. UI completa será portada quando o redesign de Overview, Traces e Avaliações for aceito.
          </div>
        </div>
        <button className="btn btn--sm btn--ghost" onClick={() => window.fireToast({ kind: "info", title: "Roadmap", msg: `Redesign de "${m.title}" planejado para fase seguinte` })}>
          Ver no roadmap <Icon name="arrowRight" size={11} />
        </button>
      </div>

      {/* Summary */}
      <section className="module-summary">
        {m.counts.map(c => (
          <div key={c.label} className="summary-card">
            <div className="summary-card__label">{c.label}</div>
            <div className="summary-card__value">{c.value}</div>
          </div>
        ))}
      </section>

      <div className="grid-detail">
        {/* Items table */}
        <Card title={`${m.title} existentes`}
              subtitle={`${m.items.length} itens preservados desta área`}
              flush>
          <table className="t">
            <thead>
              <tr>
                <th>{cols[0]}</th>
                <th>{cols[1]}</th>
                <th>{cols[2]}</th>
                <th>{cols[3]}</th>
                <th style={{ width: 32 }}></th>
              </tr>
            </thead>
            <tbody>
              {m.items.map((it, i) => (
                <tr key={i} onClick={() => window.fireToast({ kind: "info", title: `${m.title}: ${it.name}`, msg: "Detalhe — fora do redesign inicial" })}>
                  <td>
                    <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
                      <span className="t__name">{it.name}</span>
                      {moduleId === "prompts" && <span className="t__faint mono" style={{ fontSize: 10 }}>{it.versions} versões</span>}
                      {moduleId === "rubrics" && <span className="t__faint" style={{ fontSize: 10.5 }}>{window.RUBRICS.find(r => r.slug === it.name)?.desc || "—"}</span>}
                    </div>
                  </td>
                  <td>
                    {moduleId === "keys" ? (
                      <span className="mono" style={{ fontSize: 11.5, color: "var(--text-dim)" }}>{it.versions}</span>
                    ) : moduleId === "datasets" || moduleId === "exports" ? (
                      <span className="mono t__muted" style={{ fontSize: 11.5 }}>{it.versions}</span>
                    ) : (
                      <span className="mono" style={{ fontSize: 11.5, color: "var(--accent)" }}>{it.current}</span>
                    )}
                  </td>
                  <td>
                    {moduleId === "experiments" ? (
                      <Badge variant={it.current === "rodando" ? "warn" : it.current === "concluído" ? "ok" : "info"}>{it.current}</Badge>
                    ) : moduleId === "keys" ? (
                      <Badge variant={it.current === "ativa" ? "ok" : "err"}>{it.current}</Badge>
                    ) : moduleId === "exports" ? (
                      <Badge variant={it.current === "pronto" ? "ok" : it.current === "expirado" ? "default" : "warn"}>{it.current}</Badge>
                    ) : (
                      <span className="t__mono t__muted">{it.usedBy}</span>
                    )}
                  </td>
                  <td className="t__faint" style={{ fontSize: 11 }}>
                    {moduleId === "keys" || moduleId === "exports" ? `${it.lastUpdate} atrás` : it.lastUpdate}
                  </td>
                  <td>
                    {moduleId === "exports" && it.current === "pronto" ? (
                      <button className="btn btn--ghost btn--sm btn--icon"
                              onClick={e => { e.stopPropagation(); setPreviewAction("downloadExport"); }}>
                        <Icon name="download" size={12} />
                      </button>
                    ) : moduleId === "keys" && it.current === "ativa" ? (
                      <button className="btn btn--ghost btn--sm btn--icon"
                              onClick={e => { e.stopPropagation(); setPreviewAction("revokeKey"); }}
                              title="Revogar">
                        <Icon name="x" size={12} />
                      </button>
                    ) : (
                      <Icon name="chevronRight" size={12} className="t__chev" />
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>

        {/* Real endpoints column */}
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <Card title="Ações reais preservadas" subtitle="endpoints da codebase">
            <div className="endpoint-list">
              {m.endpoints.map(id => {
                const ep = window.ENDPOINTS[id];
                return (
                  <div className="endpoint-row" key={id} onClick={() => setPreviewAction(id)} style={{ cursor: "pointer" }}>
                    <span className={`endpoint-snippet__method method-${ep.method}`}>{ep.method}</span>
                    <span className="endpoint-row__path" title={ep.path}>{ep.path.replace(/^\/v1/, "")}</span>
                    <span className="endpoint-row__note">{["createExperiment", "rerunTrace", "compareTraces"].includes(id) ? "planejado" : "ativo"}</span>
                  </div>
                );
              })}
            </div>
            <div style={{ marginTop: 12, fontSize: 11, color: "var(--text-faint)" }}>
              Clique em qualquer endpoint para ver o que a ação faria.
            </div>
          </Card>

          {moduleId === "keys" && (
            <Card title="Política de segurança" subtitle="exibido no preview porque é regra real">
              <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12, color: "var(--text-muted)", lineHeight: 1.7 }}>
                <li>O segredo cru aparece <strong style={{ color: "var(--text)" }}>uma única vez</strong> na criação.</li>
                <li>Listagem mostra sempre mascarado: <span className="mono">evk_prod_••••a14f</span></li>
                <li>Revogação é imediata; chave fica histórica para auditoria.</li>
                <li>Rotação recomendada a cada 90 dias.</li>
              </ul>
            </Card>
          )}

          {moduleId === "exports" && (
            <Card title="Limites do export" subtitle="planejados pelo backend">
              <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12, color: "var(--text-muted)", lineHeight: 1.7 }}>
                <li>Máx. 100k traces por job</li>
                <li>Tamanho final 50 MB / arquivo</li>
                <li>Retenção do download: 7 dias</li>
                <li>Formato: JSONL — uma trace por linha</li>
              </ul>
            </Card>
          )}
        </div>
      </div>

      {previewAction && <PreviewActionModal endpointId={previewAction} onClose={() => setPreviewAction(null)} />}
    </div>
  );
}

Object.assign(window, { ModuleScreen });
