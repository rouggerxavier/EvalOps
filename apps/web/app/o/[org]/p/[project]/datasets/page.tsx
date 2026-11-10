import Link from "next/link";
import { AlertTriangle, CheckCircle2, CircleMinus } from "lucide-react";

import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { addDatasetItemAction, buildDatasetFromTracesAction, createDatasetAction } from "@/lib/actions";
import { getDatasetItems, getDatasets, hasAuthToken, resolveProject } from "@/lib/api";
import { safeErrorMessage } from "@/lib/safe-error";
import type { Dataset, DatasetItem } from "@/lib/types";
import { DatasetItemForm } from "./DatasetItemForm";

type Props = {
  params: Promise<{ org: string; project: string }>;
  searchParams: Promise<{
    dataset?: string;
    created?: string;
    items_added?: string;
    built?: string;
    error?: string;
  }>;
};

function sourceLabel(source: string): string {
  if (source === "manual") return "manual";
  if (source === "traces") return "traces";
  return source || "Sem dados";
}

function relativePt(iso: string): string {
  const minutes = Math.floor((Date.now() - Date.parse(iso)) / 60_000);
  if (minutes < 1) return "agora";
  if (minutes < 60) return `há ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `há ${hours} h`;
  const days = Math.floor(hours / 24);
  return days < 14 ? `há ${days} dias` : `há ${Math.floor(days / 7)} semanas`;
}

function itemQuestion(item: DatasetItem): string {
  const messages = item.input.messages;
  if (!Array.isArray(messages)) return "Sem dados";
  const message = [...messages].reverse().find((value) => {
    if (!value || typeof value !== "object") return false;
    const candidate = value as Record<string, unknown>;
    return candidate.role === "user" && typeof candidate.content === "string";
  }) as Record<string, unknown> | undefined;
  return typeof message?.content === "string" ? message.content : "Sem dados";
}

function expectedAnswer(item: DatasetItem): string {
  const answer = item.expected_output?.assistant_message;
  return typeof answer === "string" ? answer : "Sem dados";
}

function DatasetStatus({ items }: { items: DatasetItem[] }) {
  if (items.length === 0) {
    return (
      <span className="badge">
        <CircleMinus size={13} aria-hidden="true" /> Vazio
      </span>
    );
  }
  return (
    <span className="badge badge--ok">
      <CheckCircle2 size={13} aria-hidden="true" /> Pronto
    </span>
  );
}

export default async function DatasetsPage({ params, searchParams }: Props) {
  const { org, project } = await params;
  const qp = await searchParams;

  if (!(await hasAuthToken())) return <AuthRequiredPanel layout="main" />;

  const basePath = `/o/${org}/p/${project}/datasets`;
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

  const rows = datasets.map((dataset) => ({ dataset, items: itemsByDataset.get(dataset.id) ?? [] }));
  const selectedRow = rows.find((row) => row.dataset.id === qp.dataset) ?? rows[0] ?? null;
  const selectedDatasetId = selectedRow?.dataset.id ?? null;
  const selectedItems = selectedRow?.items ?? [];

  async function addDatasetItemFromFormAction(formData: FormData): Promise<void> {
    "use server";
    const question = String(formData.get("question") ?? "");
    const answer = String(formData.get("expected_answer") ?? "");
    formData.set("input_json", JSON.stringify({ messages: [{ role: "user", content: question }] }));
    formData.set("expected_output_json", answer ? JSON.stringify({ assistant_message: answer }) : "");
    formData.set("metadata_json", "{}");
    await addDatasetItemAction(formData);
  }

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1 className="page-header__title">Datasets</h1>
          <p className="page-header__subtitle">
            Perguntas com a resposta esperada, para testar a IA antes de publicar.
          </p>
        </div>
        <div className="page-header__actions ops-actions">
          <details className="ops-inline">
            <summary className="btn">Construir a partir de traces</summary>
            {rows.length > 0 ? (
              <form action={buildDatasetFromTracesAction} className="card ops-form">
                <input type="hidden" name="org" value={org} />
                <input type="hidden" name="project" value={project} />
                <label className="ops-form__field">
                  <span>Dataset</span>
                  <select name="dataset_id" defaultValue={selectedDatasetId ?? ""} required>
                    {rows.filter(({ dataset }) => dataset.task_type !== "regression").map(({ dataset }) => <option key={dataset.id} value={dataset.id}>{dataset.slug}</option>)}
                  </select>
                </label>
                <label className="ops-form__field">
                  <span>Ambiente</span>
                  <select name="environment" defaultValue="">
                    <option value="">Qualquer</option>
                    <option value="prod">Produção</option>
                    <option value="staging">Staging</option>
                    <option value="dev">Dev</option>
                  </select>
                </label>
                <label className="ops-form__field">
                  <span>Situação</span>
                  <select name="status" defaultValue="">
                    <option value="">Qualquer</option>
                    <option value="ok">Aprovado</option>
                    <option value="partial">Parcial</option>
                    <option value="error">Reprovado</option>
                  </select>
                </label>
                <input type="hidden" name="limit" value="50" />
                <p className="ops-note">
                  Escolha um dataset existente. Os traces encontrados serão adicionados a ele.
                </p>
                <button type="submit" className="btn btn--primary">Construir</button>
              </form>
            ) : (
              <div className="card ops-form">
                <p className="ops-empty">Crie um dataset antes de importar traces.</p>
              </div>
            )}
          </details>
          <details className="ops-inline">
            <summary className="btn btn--primary">Novo dataset</summary>
            <form action={createDatasetAction} className="card ops-form">
              <input type="hidden" name="org" value={org} />
              <input type="hidden" name="project" value={project} />
              <input type="hidden" name="project_id" value={resolved.project_id} />
              <input type="hidden" name="source" value="manual" />
              <label className="ops-form__field">
                <span>Nome</span>
                <input name="slug" placeholder="support-golden-set" minLength={2} pattern="[a-z0-9-]+" required />
              </label>
              <button type="submit" className="btn btn--primary">Criar dataset</button>
            </form>
          </details>
        </div>
      </header>

      {qp.error && <p className="ops-note" role="alert">{safeErrorMessage(qp.error, "Falha ao executar ação.")}</p>}
      {qp.created && <p className="ops-note" role="status">Dataset criado.</p>}
      {qp.items_added && <p className="ops-note" role="status">Item adicionado.</p>}
      {qp.built && <p className="ops-note" role="status">Dataset atualizado com traces.</p>}
      {loadError ? (
        <section className="card ops-empty" role="alert">
          <AlertTriangle size={18} aria-hidden="true" />
          <div>
            <h2>Não foi possível carregar datasets</h2>
            <p>{loadError}</p>
            <Link className="btn" href={basePath}>Tentar novamente</Link>
          </div>
        </section>
      ) : (
        <>
          <section className="card">
            <div className="table-wrap">
              <table className="t">
                <thead>
                  <tr>
                    <th>Nome</th>
                    <th>Origem</th>
                    <th className="t__num">Itens</th>
                    <th>Situação</th>
                    <th className="t__num">Criado</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.length === 0 ? (
                    <tr><td className="empty-row" colSpan={5}>Sem dados. Crie um dataset para começar.</td></tr>
                  ) : rows.map(({ dataset, items }) => {
                    const itemCount = items.length >= 100 ? "Sem dados" : items.length.toLocaleString("pt-BR");
                    return (
                      <tr key={dataset.id} className={selectedDatasetId === dataset.id ? "is-selected" : undefined}>
                        <td>
                          <Link className="t__name" href={`${basePath}?dataset=${encodeURIComponent(dataset.id)}`} aria-current={selectedDatasetId === dataset.id ? "page" : undefined}>
                            {dataset.slug}
                          </Link>
                        </td>
                        <td>{sourceLabel(dataset.source)}</td>
                        <td className="t__num" title={items.length >= 100 ? "A API retorna até 100 itens por consulta; total exato indisponível." : undefined}>{itemCount}</td>
                        <td><DatasetStatus items={items} /></td>
                        <td className="t__num">{relativePt(dataset.created_at)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>

          <section className="card">
            <div className="card__header">
              <h2 className="card__title">Itens de {selectedRow?.dataset.slug ?? "Sem dados"}</h2>
              {selectedRow && selectedRow.dataset.task_type !== "regression" ? (
                <details className="ops-inline">
                  <summary className="btn">Adicionar item</summary>
                  <DatasetItemForm org={org} project={project} datasetId={selectedRow.dataset.id} action={addDatasetItemFromFormAction} />
                </details>
              ) : null}
            </div>
            {selectedRow && selectedItems.length > 0 ? (
              <div className="table-wrap">
                {selectedItems.length >= 100 ? <p className="ops-note">A API retorna até 100 itens por consulta. Total exato: Sem dados.</p> : null}
                <table className="t">
                  <thead>
                    <tr><th>Nº</th><th>{selectedRow.dataset.task_type === "regression" ? "Input tabular" : "Pergunta"}</th><th>Referência esperada</th><th className="t__num">Criado</th></tr>
                  </thead>
                  <tbody>
                    {selectedItems.slice(0, 100).map((item) => (
                      <tr key={item.id}>
                        <td>{item.ord + 1}</td>
                        <td>{selectedRow.dataset.task_type === "regression" ? JSON.stringify(item.input) : itemQuestion(item)}</td>
                        <td>{selectedRow.dataset.task_type === "regression" ? String(item.expected_output?.value ?? "Sem referência") : expectedAnswer(item)}</td>
                        <td className="t__num">{relativePt(item.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="ops-empty">{selectedRow ? "Este dataset ainda não tem itens." : "Sem dados. Selecione ou crie um dataset."}</p>
            )}
          </section>
        </>
      )}
    </div>
  );
}
