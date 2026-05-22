import Link from "next/link";
import { ChevronRight, Plus, RefreshCw, Upload } from "lucide-react";

import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { addDatasetItemAction, buildDatasetFromTracesAction, createDatasetAction } from "@/lib/actions";
import { getDatasetItems, getDatasets, hasAuthToken, resolveProject } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { safeErrorMessage } from "@/lib/safe-error";
import type { Dataset, DatasetItem } from "@/lib/types";

type Props = {
  params: Promise<{ org: string; project: string }>;
  searchParams: Promise<{
    source?: string;
    dataset?: string;
    created?: string;
    items_added?: string;
    built?: string;
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

const TEXTAREA_STYLE: React.CSSProperties = {
  ...INPUT_STYLE,
  minHeight: 84,
  resize: "vertical",
  fontFamily: "var(--font-mono)",
  fontSize: 12,
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

function relTime(iso: string): string {
  const diff = Date.now() - Date.parse(iso);
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "agora";
  if (mins < 60) return `${mins}m atrás`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h atrás`;
  return `${Math.floor(hrs / 24)}d atrás`;
}

function sourceLabel(source: string): string {
  if (source === "manual") return "manual";
  if (source === "traces") return "traces";
  return source || "unknown";
}

function statusForDataset(dataset: Dataset, items: DatasetItem[]): { cls: string; label: string } {
  if (items.length === 0) return { cls: "", label: "vazio" };
  if (dataset.source === "traces") return { cls: "badge--ok", label: "pronto" };
  if (dataset.source === "manual") return { cls: "badge--info", label: "curado" };
  return { cls: "badge--warn", label: "ativo" };
}

function queryString(values: Record<string, string | undefined>): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) {
    if (value) query.set(key, value);
  }
  const asString = query.toString();
  return asString ? `?${asString}` : "";
}

function shortJson(value: Record<string, unknown> | null | undefined): string {
  if (!value) return "null";
  const full = JSON.stringify(value);
  if (full.length <= 120) return full;
  return `${full.slice(0, 117)}...`;
}

export default async function DatasetsPage({ params, searchParams }: Props) {
  const { org, project } = await params;
  const qp = await searchParams;

  if (!(await hasAuthToken())) {
    return <AuthRequiredPanel layout="main" />;
  }

  const basePath = `/o/${org}/p/${project}/datasets`;
  const sourceFilter = qp.source ?? "all";

  const resolved = await resolveProject(org, project);
  let datasets: Dataset[] = [];
  let itemsByDataset = new Map<string, DatasetItem[]>();
  let loadError: string | null = null;

  try {
    const datasetsRes = await getDatasets(resolved.project_id);
    datasets = datasetsRes.data;
    itemsByDataset = new Map(
      await Promise.all(
        datasets.map(async (dataset) => [dataset.id, (await getDatasetItems(dataset.id)).data] as const),
      ),
    );
  } catch (error) {
    loadError = safeErrorMessage(error, "Falha ao carregar datasets.");
  }

  if (loadError) {
    return (
      <div className="page">
        <div className="page-header">
          <div>
            <p className="page-header__eyebrow">Dados · Datasets</p>
            <h1 className="page-header__title">Datasets</h1>
            <p className="page-header__subtitle">
              Conjuntos para avaliacoes, regressao e fine-tuning.
            </p>
          </div>
          <div className="page-header__actions">
            <Link href={basePath} className="btn btn--sm">
              <RefreshCw size={13} />
              Tentar novamente
            </Link>
          </div>
        </div>
        <div style={alertStyle("err")}>
          Nao foi possivel carregar datasets. Detalhe: {loadError}
        </div>
      </div>
    );
  }

  const rows = datasets.map((dataset) => ({
    dataset,
    items: itemsByDataset.get(dataset.id) ?? [],
  }));
  const filteredRows = rows.filter(({ dataset }) => (
    sourceFilter === "all" ? true : dataset.source === sourceFilter
  ));

  const selectedDatasetId = qp.dataset ?? filteredRows[0]?.dataset.id ?? rows[0]?.dataset.id ?? null;
  const selectedRow = rows.find((row) => row.dataset.id === selectedDatasetId) ?? null;
  const selectedItems = selectedRow?.items ?? [];

  const totalItems = rows.reduce((acc, row) => acc + row.items.length, 0);
  const traceDatasets = rows.filter((row) => row.dataset.source === "traces").length;
  const readyDatasets = rows.filter((row) => row.items.length > 0).length;
  const latestActivity = (() => {
    let mostRecent: string | null = null;
    for (const { dataset, items } of rows) {
      if (!mostRecent || Date.parse(dataset.created_at) > Date.parse(mostRecent)) {
        mostRecent = dataset.created_at;
      }
      for (const item of items) {
        if (!mostRecent || Date.parse(item.created_at) > Date.parse(mostRecent)) {
          mostRecent = item.created_at;
        }
      }
    }
    return mostRecent;
  })();

  const tabHref = (source: string) =>
    `${basePath}${queryString({
      source: source === "all" ? undefined : source,
      dataset: selectedDatasetId ?? undefined,
    })}`;

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <p className="page-header__eyebrow">Dados · Datasets</p>
          <h1 className="page-header__title">Datasets</h1>
          <p className="page-header__subtitle">
            Curadoria de conjuntos para avaliacoes, regressoes e fine-tuning.
          </p>
        </div>
        <div className="page-header__actions">
          <Link href="#dataset-create" className="btn btn--sm">
            <Plus size={13} />
            Novo dataset
          </Link>
          <Link href={basePath + queryString({ source: qp.source, dataset: selectedDatasetId ?? undefined })} className="btn btn--sm">
            <RefreshCw size={13} />
            Atualizar
          </Link>
        </div>
      </div>

      {qp.error && <div style={alertStyle("err")}>{qp.error}</div>}
      {qp.created && <div style={alertStyle("ok")}>Dataset criado com sucesso.</div>}
      {qp.items_added && <div style={alertStyle("ok")}>Item adicionado ao dataset.</div>}
      {qp.built && <div style={alertStyle("ok")}>Dataset atualizado com traces do backend.</div>}

      {/* Summary row — só dados reais do payload */}
      <section className="module-summary" aria-label="Resumo de datasets">
        <div className="summary-card">
          <p className="summary-card__label">Datasets</p>
          <div className="summary-card__value">{rows.length.toLocaleString("pt-BR")}</div>
          <div className="summary-card__hint">total no projeto</div>
        </div>
        <div className="summary-card">
          <p className="summary-card__label">Itens</p>
          <div className="summary-card__value">{totalItems.toLocaleString("pt-BR")}</div>
          <div className="summary-card__hint">exemplos registrados</div>
        </div>
        <div className="summary-card">
          <p className="summary-card__label">Fonte traces</p>
          <div className="summary-card__value">{traceDatasets.toLocaleString("pt-BR")}</div>
          <div className="summary-card__hint">datasets de traces · {readyDatasets} prontos</div>
        </div>
        <div className="summary-card">
          <p className="summary-card__label">Última atividade</p>
          <div className="summary-card__value">
            {latestActivity ? relTime(latestActivity) : "—"}
          </div>
          <div className="summary-card__hint">dataset ou item</div>
        </div>
      </section>

      <nav className="tabs">
        <Link href={tabHref("all")} className={`tab${sourceFilter === "all" ? " is-active" : ""}`}>
          Todos
          <span className="tab__count">{rows.length}</span>
        </Link>
        <Link href={tabHref("manual")} className={`tab${sourceFilter === "manual" ? " is-active" : ""}`}>
          Manual
          <span className="tab__count">
            {rows.filter((row) => row.dataset.source === "manual").length}
          </span>
        </Link>
        <Link href={tabHref("traces")} className={`tab${sourceFilter === "traces" ? " is-active" : ""}`}>
          Traces
          <span className="tab__count">
            {rows.filter((row) => row.dataset.source === "traces").length}
          </span>
        </Link>
      </nav>

      <div className="grid-detail">
        <div style={{ minWidth: 0 }}>
          <section className="card">
            <div className="card__header">
              <h3 className="card__title">Lista de datasets</h3>
              <span className="t__faint" style={{ fontSize: 11 }}>
                {filteredRows.length} visivel(is)
              </span>
            </div>
            <div className="card__body card__body--flush">
              <div style={{ overflowX: "auto" }}>
                <table className="t">
                  <thead>
                    <tr>
                      <th>Nome</th>
                      <th>Origem</th>
                      <th>Itens</th>
                      <th>Status</th>
                      <th>Criado em</th>
                      <th style={{ width: 32 }} />
                    </tr>
                  </thead>
                  <tbody>
                    {filteredRows.length === 0 ? (
                      <tr>
                        <td className="empty-row" colSpan={6}>
                          Nenhum dataset com esse filtro.
                        </td>
                      </tr>
                    ) : (
                      filteredRows.map(({ dataset, items }) => {
                        const status = statusForDataset(dataset, items);
                        const isSelected = selectedDatasetId === dataset.id;
                        return (
                          <tr key={dataset.id} style={isSelected ? { background: "var(--accent-bg)" } : undefined}>
                            <td>
                              <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                                <span className="t__name">{dataset.slug}</span>
                                <span style={{ fontSize: 11, color: "var(--text-faint)" }}>
                                  {dataset.description ?? "Sem descricao"}
                                </span>
                              </div>
                            </td>
                            <td>
                              <span className="tag">{sourceLabel(dataset.source)}</span>
                            </td>
                            <td className="t__num">{items.length.toLocaleString("pt-BR")}</td>
                            <td>
                              <span className={`badge ${status.cls}`}>
                                <span className="badge__dot" />
                                {status.label}
                              </span>
                            </td>
                            <td className="t__muted" style={{ fontSize: 12 }}>
                              {formatDateTime(dataset.created_at)}
                            </td>
                            <td>
                              <Link
                                href={
                                  basePath +
                                  queryString({
                                    source: sourceFilter === "all" ? undefined : sourceFilter,
                                    dataset: dataset.id,
                                  })
                                }
                                style={{ color: "var(--text-faint)", display: "flex" }}
                              >
                                <ChevronRight size={14} />
                              </Link>
                            </td>
                          </tr>
                        );
                      })
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </section>

          {filteredRows.length === 0 && (
            <section className="card" style={{ marginTop: 12 }}>
              <div className="card__body">
                <p style={{ marginTop: 0, marginBottom: 8, color: "var(--text)", fontWeight: 600 }}>
                  Datasets alimentam avaliacoes, regressao e fine-tuning.
                </p>
                <p style={{ marginTop: 0, marginBottom: 16, color: "var(--text-muted)", fontSize: 13 }}>
                  Crie um dataset manual ou monte um conjunto a partir de traces reais do projeto.
                </p>
                <ol style={{ margin: 0, paddingLeft: 18, color: "var(--text-muted)", fontSize: 13, lineHeight: 1.8 }}>
                  <li>Crie o dataset com slug estavel.</li>
                  <li>Adicione exemplos manualmente ou via traces.</li>
                  <li>Use em experiments e avaliacoes.</li>
                </ol>
              </div>
            </section>
          )}

          {selectedRow && selectedItems.length > 0 && (
            <section className="card" style={{ marginTop: 12 }}>
              <div className="card__header">
                <h3 className="card__title">Previa de itens - {selectedRow.dataset.slug}</h3>
                <span className="t__faint" style={{ fontSize: 11 }}>
                  {selectedItems.length.toLocaleString("pt-BR")} item(ns)
                </span>
              </div>
              <div className="card__body card__body--flush">
                <div style={{ overflowX: "auto" }}>
                  <table className="t">
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>Input</th>
                        <th>Output esperado</th>
                        <th>Criado em</th>
                      </tr>
                    </thead>
                    <tbody>
                      {selectedItems.slice(0, 6).map((item) => (
                        <tr key={item.id}>
                          <td className="t__num">{item.ord}</td>
                          <td className="mono t__muted" style={{ maxWidth: 280 }}>
                            <span title={JSON.stringify(item.input)}>{shortJson(item.input)}</span>
                          </td>
                          <td className="mono t__muted" style={{ maxWidth: 280 }}>
                            <span title={JSON.stringify(item.expected_output)}>{shortJson(item.expected_output)}</span>
                          </td>
                          <td className="t__muted" style={{ fontSize: 12 }}>{formatDateTime(item.created_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </section>
          )}
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <section id="dataset-create" className="card">
            <div className="card__header">
              <h3 className="card__title">Criar dataset</h3>
              <span className="t__faint" style={{ fontSize: 11 }}>acao real</span>
            </div>
            <div className="card__body">
              <form action={createDatasetAction} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                <input type="hidden" name="org" value={org} />
                <input type="hidden" name="project" value={project} />
                <input type="hidden" name="project_id" value={resolved.project_id} />

                <label style={LABEL_STYLE}>
                  <span style={{ color: "var(--text-muted)" }}>Slug</span>
                  <input name="slug" placeholder="support-golden-set" required style={INPUT_STYLE} />
                </label>
                <label style={LABEL_STYLE}>
                  <span style={{ color: "var(--text-muted)" }}>Descricao</span>
                  <input name="description" placeholder="Golden set para suporte" style={INPUT_STYLE} />
                </label>
                <label style={LABEL_STYLE}>
                  <span style={{ color: "var(--text-muted)" }}>Fonte</span>
                  <select name="source" defaultValue="manual" style={INPUT_STYLE}>
                    <option value="manual">manual</option>
                    <option value="traces">traces</option>
                  </select>
                </label>
                <button type="submit" className="btn btn--primary" style={{ alignSelf: "flex-start" }}>
                  <Plus size={13} />
                  Criar dataset
                </button>
              </form>
            </div>
          </section>

          {selectedRow ? (
            <>
              <section className="card">
                <div className="card__header">
                  <h3 className="card__title">Adicionar item - {selectedRow.dataset.slug}</h3>
                  <span className="t__faint" style={{ fontSize: 11 }}>
                    backend: /datasets/{selectedRow.dataset.id}/items
                  </span>
                </div>
                <div className="card__body">
                  <form action={addDatasetItemAction} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    <input type="hidden" name="org" value={org} />
                    <input type="hidden" name="project" value={project} />
                    <input type="hidden" name="dataset_id" value={selectedRow.dataset.id} />
                    <label style={LABEL_STYLE}>
                      <span style={{ color: "var(--text-muted)" }}>Input JSON</span>
                      <textarea
                        name="input_json"
                        defaultValue='{"messages":[{"role":"user","content":"Como resetar minha senha?"}]}'
                        style={TEXTAREA_STYLE}
                      />
                    </label>
                    <label style={LABEL_STYLE}>
                      <span style={{ color: "var(--text-muted)" }}>Output esperado JSON</span>
                      <textarea
                        name="expected_output_json"
                        defaultValue='{"assistant_message":"Use o fluxo de reset da pagina de login."}'
                        style={TEXTAREA_STYLE}
                      />
                    </label>
                    <label style={LABEL_STYLE}>
                      <span style={{ color: "var(--text-muted)" }}>Metadata JSON</span>
                      <textarea name="metadata_json" defaultValue={"{}"} style={TEXTAREA_STYLE} />
                    </label>
                    <button type="submit" className="btn btn--primary" style={{ alignSelf: "flex-start" }}>
                      Adicionar item
                    </button>
                  </form>
                </div>
              </section>

              <section id="dataset-build" className="card">
                <div className="card__header">
                  <h3 className="card__title">Construir a partir de traces</h3>
                  <span className="t__faint" style={{ fontSize: 11 }}>acao real</span>
                </div>
                <div className="card__body">
                  <form action={buildDatasetFromTracesAction} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    <input type="hidden" name="org" value={org} />
                    <input type="hidden" name="project" value={project} />
                    <input type="hidden" name="dataset_id" value={selectedRow.dataset.id} />
                    <label style={LABEL_STYLE}>
                      <span style={{ color: "var(--text-muted)" }}>Ambiente</span>
                      <select name="environment" defaultValue="" style={INPUT_STYLE}>
                        <option value="">qualquer</option>
                        <option value="dev">dev</option>
                        <option value="staging">staging</option>
                        <option value="prod">prod</option>
                      </select>
                    </label>
                    <label style={LABEL_STYLE}>
                      <span style={{ color: "var(--text-muted)" }}>Status</span>
                      <select name="status" defaultValue="" style={INPUT_STYLE}>
                        <option value="">qualquer</option>
                        <option value="ok">ok</option>
                        <option value="partial">partial</option>
                        <option value="error">error</option>
                      </select>
                    </label>
                    <label style={LABEL_STYLE}>
                      <span style={{ color: "var(--text-muted)" }}>Limite</span>
                      <input name="limit" type="number" min={1} max={500} defaultValue={50} style={INPUT_STYLE} />
                    </label>
                    <button type="submit" className="btn btn--primary" style={{ alignSelf: "flex-start" }}>
                      <Upload size={13} />
                      Ingerir traces
                    </button>
                  </form>
                </div>
              </section>

              <section className="card">
                <div className="card__header">
                  <h3 className="card__title">Acoes nao disponiveis no contrato atual</h3>
                </div>
                <div className="card__body" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  <button type="button" className="btn btn--sm" disabled style={{ justifyContent: "flex-start", opacity: 0.55 }}>
                    Exportar dataset
                  </button>
                  <p style={{ margin: 0, color: "var(--text-faint)", fontSize: 12 }}>
                    O backend atual nao expone endpoint para exportar ou remover datasets pelo dashboard.
                  </p>
                </div>
              </section>
            </>
          ) : (
            <section className="card">
              <div className="card__body">
                <p style={{ margin: 0, color: "var(--text-faint)", fontSize: 13 }}>
                  Selecione um dataset para ver detalhes e acoes operacionais.
                </p>
              </div>
            </section>
          )}
        </div>
      </div>

    </div>
  );
}

