import Link from "next/link";
import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { hasAuthToken, resolveProject, taskRead } from "@/lib/api";
import type { ImportedExecution } from "@/lib/execution-types";
import { PlanForm } from "./plans/PlanForm";
import type { ExecutionPlan } from "@/lib/execution-types";
import { ImportForm } from "./ImportForm";
export default async function ExecutionsPage({ params }: { params: Promise<{ org: string; project: string }> }) {
  if (!(await hasAuthToken())) return <AuthRequiredPanel layout="main" />;
  const { org, project } = await params;
  const resolved = await resolveProject(org, project);
  const capabilities = await taskRead<{ permissions: string[] }>(`/projects/${resolved.project_id}/capabilities`);
  const result = await taskRead<{ data: ImportedExecution[] }>(`/projects/${resolved.project_id}/executions`);
  const plans = await taskRead<{ data: ExecutionPlan[] }>(`/projects/${resolved.project_id}/execution-plans`);
  const base = `/o/${org}/p/${project}/evaluations`;
  return <div className="page ops-page"><header className="ops-page-header"><div><h1>Execuções e evidências</h1><p>Capturas externas e execuções admitidas têm origem e orçamento distintos. Nenhum código executa no processo API.</p></div><div><Link href={`${base}/runners`}>Gerenciar runners</Link> · <Link href={base}>Avaliações</Link></div></header>
    <section className="card"><h2>Capturas importadas</h2><div className="table-wrap"><table className="t"><thead><tr><th>Execução</th><th>Modo declarado</th><th>Ambiente</th><th>Origem</th><th>Status técnico</th></tr></thead><tbody>{result.data.map(row => <tr key={row.id}><td><Link href={`${base}/executions/${row.id}`}>{row.id}</Link></td><td>{row.mode}</td><td>{row.environment}</td><td>{row.capture_origin === "external_import" ? "Importada" : "Controlada"}</td><td>{row.status}</td></tr>)}</tbody></table></div>{!result.data.length && <p>Nenhuma captura importada.</p>}</section>
    <section className="card"><h2>Planos selados</h2><ul>{plans.data.map(plan => <li key={plan.id}><Link href={`${base}/executions/plans/${plan.id}`}>{plan.id}</Link> · {plan.environment}</li>)}</ul></section>
    {capabilities.permissions.includes("write") && <section className="card"><h2>Preparar execução</h2><PlanForm org={org} project={project} /></section>}
    {capabilities.permissions.includes("write") && <section className="card"><h2>Importar captura externa</h2><ImportForm org={org} project={project} /></section>}
  </div>;
}
