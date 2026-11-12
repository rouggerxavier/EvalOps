import Link from "next/link";
import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { hasAuthToken, resolveProject, taskRead, getDatasets } from "@/lib/api";
import { getActiveEnvironment } from "@/lib/active-env";
import { CaptureLink } from "./CaptureLink";
export default async function FailuresPage({ params }: { params: Promise<{ org: string; project: string }> }) {
  if (!(await hasAuthToken())) return <AuthRequiredPanel layout="main" />;
  const { org, project } = await params;
  const resolved = await resolveProject(org, project);
  const capabilities = await taskRead<{ permissions: string[] }>(`/projects/${resolved.project_id}/capabilities`);
  const environment = await getActiveEnvironment(undefined);
  const failures = await taskRead<{ data: { id: string; name: string; environment: string; category: string }[] }>(`/projects/${resolved.project_id}/failures?kind=trace${environment ? `&environment=${environment}` : ""}`);
  const datasets = (await getDatasets(resolved.project_id)).data.filter(row => !row.task_type || row.task_type === "text");
  return <div className="page ops-page"><header className="ops-page-header"><h1>Falhas observadas</h1><Link href={`/o/${org}/p/${project}/evaluations/investigations`}>Investigações</Link></header>
    <section className="card"><h2>Evidências para curadoria</h2><p>Erro técnico não significa reprovação do modelo. Referências copiadas permanecem em rascunho até revisão humana.</p>
      {!failures.data.length && <p>Sem falhas registradas no projeto.</p>}
      {failures.data.map(row => <details key={row.id}><summary>{row.name} · {row.environment} · {row.category === "technical" ? "Erro técnico" : "Sinal legado de qualidade"}</summary><p><Link href={`/o/${org}/p/${project}/traces/${row.id}`}>Abrir trace</Link></p>{capabilities.permissions.includes("write") && <CaptureLink org={org} project={project} trace={row.id} datasets={datasets} />}</details>)}
      <Link href={`/o/${org}/p/${project}/datasets`}>Criar ou revisar datasets</Link>
    </section>
  </div>;
}
