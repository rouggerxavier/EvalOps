import Link from "next/link";
import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { hasAuthToken, resolveProject, taskRead } from "@/lib/api";
import { getActiveEnvironment } from "@/lib/active-env";
import { taskDecisionLabels } from "@/lib/task-types";
import type { TaskEvaluation } from "@/lib/task-types";
import { ComparisonForm } from "./ComparisonForm";
import { RegressionForm } from "./RegressionForm";

export default async function TasksPage({ params }: { params: Promise<{ org: string; project: string }> }) {
  if (!(await hasAuthToken())) return <AuthRequiredPanel layout="main" />;
  const { org, project } = await params;
  const resolved = await resolveProject(org, project);
  const activeEnvironment = await getActiveEnvironment(undefined);
  const environment = activeEnvironment ?? "dev";
  const capabilities = await taskRead<{ permissions: string[] }>(`/projects/${resolved.project_id}/capabilities`);
  const response = await taskRead<{ data: TaskEvaluation[] }>(`/projects/${resolved.project_id}/task-evaluations${activeEnvironment ? `?environment=${activeEnvironment}` : ""}`);
  const datasets = await taskRead<{ data: { id: string; slug: string; task_type?: string }[] }>(`/projects/${resolved.project_id}/datasets`);
  const snapshotGroups = await Promise.all(datasets.data.filter(row => row.task_type === "regression").map(async dataset => {
    const result = await taskRead<{ data: { id: string; item_count: number }[] }>(`/datasets/${dataset.id}/snapshots`);
    return result.data.map(row => ({ id: row.id, label: `${dataset.slug} · ${row.item_count} amostras · ${row.id}` }));
  }));
  const modelResponse = await taskRead<{ data: { id: string; name: string; version_ref: string; task_type: string }[] }>(`/projects/${resolved.project_id}/model-versions`);
  const base = `/o/${org}/p/${project}/evaluations`;
  return <div className="page ops-page">
    <header className="ops-page-header"><div><h1>Regressão offline</h1><p>Importe referências e predições. API, SDK e interface consultam os mesmos resultados persistidos.</p></div><div><Link href={`${base}/tasks/classification`}>Classificação offline</Link> · <Link href={base}>Avaliações de traces</Link></div></header>
    {capabilities.permissions.includes("write") && <section className="card"><h2>Nova avaliação</h2><RegressionForm org={org} project={project} environment={environment} snapshots={snapshotGroups.flat()} models={modelResponse.data.filter(row => row.task_type === "regression")} /></section>}
    {capabilities.permissions.includes("evaluate") && response.data.length >= 2 && <section className="card"><h2>Comparar versões</h2><ComparisonForm org={org} project={project} evaluations={response.data.filter(row => row.evaluator_manifest.id === "regression.standard")} /></section>}
    <section className="card"><h2>Avaliações por tarefa</h2><div className="table-wrap"><table className="t"><thead><tr><th>Avaliação</th><th>Ambiente</th><th>Status</th><th>Decisão</th><th>Pares válidos</th><th>Cobertura</th></tr></thead><tbody>
      {response.data.map(row => <tr key={row.id}><td><Link href={`${base}/tasks/${row.id}`}>{row.id}</Link></td><td>{row.environment}</td><td>{row.status}</td><td>{row.decision ? taskDecisionLabels[row.decision] : "Aguardando decisão"}</td><td>{row.n_valid}/{row.n_total}</td><td>{row.coverage === null ? "Sem população" : `${(row.coverage * 100).toLocaleString("pt-BR")}%`}</td></tr>)}
    </tbody></table></div>{!response.data.length && <p>Nenhuma avaliação neste ambiente.</p>}</section>
  </div>;
}
