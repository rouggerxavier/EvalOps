import Link from "next/link";
import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { hasAuthToken, resolveProject, taskRead } from "@/lib/api";
import type { ExecutionPlan } from "@/lib/execution-types";
import { PlanForm } from "../PlanForm";
export default async function PlanPage({ params }: { params: Promise<{ org: string; project: string; id: string }> }) {
  if (!(await hasAuthToken())) return <AuthRequiredPanel layout="main" />;
  const { org, project, id } = await params;
  const resolved = await resolveProject(org, project);
  const plan = await taskRead<ExecutionPlan>(`/execution-plans/${encodeURIComponent(id)}`);
  if (plan.project_id !== resolved.project_id) throw new Error("Plano não pertence ao projeto.");
  const capabilities = await taskRead<{ permissions: string[] }>(`/projects/${resolved.project_id}/capabilities`);
  return <div className="page ops-page"><header className="ops-page-header"><div><h1>Plano selado</h1><p style={{ overflowWrap: "anywhere" }}>{plan.id} · {plan.environment}</p></div><Link href={`/o/${org}/p/${project}/evaluations/executions`}>Execuções</Link></header>
    <section className="card"><h2>Manifest e autoridade</h2><p style={{ overflowWrap: "anywhere" }}>Hash: {plan.manifest_hash}</p><p style={{ overflowWrap: "anywhere" }}>Runner: {plan.runner_id}</p><p style={{ overflowWrap: "anywhere" }}>Política: {plan.policy_revision_id}. Budget da organização: {plan.organization_budget_revision_id}.</p><pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{JSON.stringify(plan.manifest, null, 2)}</pre></section>
    {capabilities.permissions.includes("write") && capabilities.permissions.includes("evaluate") && <section className="card"><h2>Admitir execução</h2><PlanForm org={org} project={project} id={id} intent="enqueue" /></section>}
  </div>;
}
