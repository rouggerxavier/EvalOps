import Link from "next/link";
import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { hasAuthToken, resolveProject, taskRead } from "@/lib/api";
import type { ImportedExecution } from "@/lib/execution-types";
import { ImportForm } from "./ImportForm";
export default async function ExecutionsPage({ params }: { params: Promise<{ org: string; project: string }> }) {
  if (!(await hasAuthToken())) return <AuthRequiredPanel layout="main" />;
  const { org, project } = await params;
  const resolved = await resolveProject(org, project);
  const capabilities = await taskRead<{ permissions: string[] }>(`/projects/${resolved.project_id}/capabilities`);
  const result = await taskRead<{ data: ImportedExecution[] }>(`/projects/${resolved.project_id}/executions`);
  const base = `/o/${org}/p/${project}/evaluations`;
  return <div className="page ops-page"><header className="ops-page-header"><div><h1>Evidências de execução</h1><p>Capturas externas declaradas pelo produtor. Nenhum processo é iniciado nesta tela.</p></div><div><Link href={`${base}/runners`}>Gerenciar runners</Link> · <Link href={base}>Avaliações</Link></div></header>
    <section className="card"><h2>Capturas importadas</h2><div className="table-wrap"><table className="t"><thead><tr><th>Execução</th><th>Modo declarado</th><th>Ambiente</th><th>Status declarado</th></tr></thead><tbody>{result.data.map(row => <tr key={row.id}><td><Link href={`${base}/executions/${row.id}`}>{row.id}</Link></td><td>{row.mode}</td><td>{row.environment}</td><td>{row.status}</td></tr>)}</tbody></table></div>{!result.data.length && <p>Nenhuma captura importada.</p>}</section>
    {capabilities.permissions.includes("write") && <section className="card"><h2>Importar captura externa</h2><ImportForm org={org} project={project} /></section>}
  </div>;
}
