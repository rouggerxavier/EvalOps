import Link from "next/link";
import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { hasAuthToken, resolveProject, taskRead } from "@/lib/api";
import { getActiveEnvironment } from "@/lib/active-env";
import type { Investigation } from "@/lib/investigation-types";
import { InvestigationForm } from "./InvestigationForm";
export default async function InvestigationsPage({ params }: { params: Promise<{ org: string; project: string }> }) {
  if (!(await hasAuthToken())) return <AuthRequiredPanel layout="main" />;
  const { org, project } = await params;
  const resolved = await resolveProject(org, project);
  const capabilities = await taskRead<{ permissions: string[] }>(`/projects/${resolved.project_id}/capabilities`);
  const { data } = await taskRead<{ data: Investigation[] }>(`/projects/${resolved.project_id}/investigations`);
  return <div className="page ops-page"><header className="ops-page-header"><h1>Investigações</h1><Link href={`/o/${org}/p/${project}/evaluations`}>Avaliações</Link></header>
    <section className="card"><h2>Investigações do projeto</h2><div className="table-wrap"><table className="t"><thead><tr><th>Título</th><th>Ambiente</th><th>Revisão</th><th>Situação</th><th>Autor</th></tr></thead><tbody>{data.map(row => <tr key={row.id}><td><Link href={`/o/${org}/p/${project}/evaluations/investigations/${row.id}`}>{row.title}</Link></td><td>{row.environment}</td><td>{row.revision}</td><td>{row.status === "open" ? "Aberta" : "Resolvida"}</td><td>{row.author_kind === "service" ? "Principal de serviço" : "Humano"}</td></tr>)}</tbody></table></div>{!data.length && <p>Nenhuma investigação. Salve evidências e próximos passos para retomar pelo mesmo ID.</p>}</section>
    {capabilities.permissions.includes("write") && <section className="card"><h2>Nova investigação</h2><InvestigationForm org={org} project={project} environment={(await getActiveEnvironment(undefined)) ?? "dev"} /></section>}
  </div>;
}
