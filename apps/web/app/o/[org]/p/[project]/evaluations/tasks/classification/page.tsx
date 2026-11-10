import Link from "next/link";
import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { hasAuthToken, resolveProject, taskRead } from "@/lib/api";
import { getActiveEnvironment } from "@/lib/active-env";
import { ClassificationForm } from "./ClassificationForm";
export default async function ClassificationPage({ params }: { params: Promise<{ org: string; project: string }> }) {
  if (!(await hasAuthToken())) return <AuthRequiredPanel layout="main" />;
  const { org, project } = await params;
  const resolved = await resolveProject(org, project);
  const capabilities = await taskRead<{ permissions: string[] }>(`/projects/${resolved.project_id}/capabilities`);
  const datasets = await taskRead<{ data: { id: string; slug: string; task_type: string }[] }>(`/projects/${resolved.project_id}/datasets`);
  const snapshots = (await Promise.all(datasets.data.filter(row => row.task_type === "classification").map(async dataset => {
    const result = await taskRead<{ data: { id: string; item_count: number }[] }>(`/datasets/${dataset.id}/snapshots`);
    return result.data.map(row => ({ id: row.id, label: `${dataset.slug} · ${row.item_count} amostras · ${row.id}` }));
  }))).flat();
  const models = await taskRead<{ data: { id: string; name: string; version_ref: string; task_type: string }[] }>(`/projects/${resolved.project_id}/model-versions`);
  return <div className="page ops-page"><header className="ops-page-header"><div><h1>Classificação offline</h1><p>Matriz, métricas por classe e calibração calculadas pela API. Nenhum modelo é executado.</p></div><Link href={`/o/${org}/p/${project}/evaluations/tasks`}>Avaliações por tarefa</Link></header>
    {capabilities.permissions.includes("write") ? <section className="card"><h2>Nova avaliação de classificação</h2><ClassificationForm org={org} project={project} environment={(await getActiveEnvironment(undefined)) ?? "dev"} snapshots={snapshots} models={models.data.filter(row => row.task_type === "classification")} /></section> : <p>Sem permissão de escrita.</p>}
  </div>;
}
