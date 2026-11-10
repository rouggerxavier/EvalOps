import Link from "next/link";
import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { hasAuthToken, resolveProject, taskRead } from "@/lib/api";
import type { Investigation } from "@/lib/investigation-types";
import { InvestigationForm } from "../InvestigationForm";
export default async function InvestigationPage({ params }: { params: Promise<{ org: string; project: string; id: string }> }) {
  if (!(await hasAuthToken())) return <AuthRequiredPanel layout="main" />;
  const { org, project, id } = await params;
  const resolved = await resolveProject(org, project);
  const current = await taskRead<Investigation>(`/investigations/${encodeURIComponent(id)}`);
  if (current.project_id !== resolved.project_id) throw new Error("Investigação não pertence ao projeto.");
  const capabilities = await taskRead<{ permissions: string[] }>(`/projects/${resolved.project_id}/capabilities`);
  const { data: history } = await taskRead<{ data: Investigation[] }>(`/investigations/${encodeURIComponent(id)}/revisions`);
  return <div className="page ops-page"><header className="ops-page-header"><div><h1>{current.title}</h1><p>Revisão {current.revision} · {current.environment} · {current.author_kind === "service" ? "Principal de serviço" : "Humano"}</p></div><Link href={`/o/${org}/p/${project}/evaluations/investigations`}>Todas as investigações</Link></header>
    {capabilities.permissions.includes("write") ? <section className="card"><h2>Continuar investigação</h2><InvestigationForm key={current.revision} org={org} project={project} current={current} /></section> : <section className="card"><h2>Resumo</h2><p>{current.summary || "Sem resumo."}</p><h3>Próximos passos</h3><ul>{current.next_steps.map((step, i) => <li key={i}>{step}</li>)}</ul></section>}
    <section className="card"><h2>Histórico imutável</h2>{history.map(row => <details key={row.revision}><summary>Revisão {row.revision}: {row.title} · {row.author_kind === "service" ? "Serviço" : "Humano"}</summary><p>{row.summary}</p><h3>Evidências</h3><ul>{row.evidence_refs.map(ref => <li key={ref}><Evidence reference={ref} org={org} project={project} /></li>)}</ul><h3>Próximos passos</h3><ul>{row.next_steps.map((step, i) => <li key={i}>{step}</li>)}</ul></details>)}</section>
  </div>;
}

function Evidence({ reference, org, project }: { reference: string; org: string; project: string }) {
  const [kind, id] = reference.split(":", 2);
  const suffix = kind === "evaluation" ? `evaluations/tasks/${encodeURIComponent(id)}` : kind === "trace" ? `traces/${encodeURIComponent(id)}` : null;
  return suffix ? <Link href={`/o/${org}/p/${project}/${suffix}`}>{reference}</Link> : <code style={{ overflowWrap: "anywhere" }}>{reference}</code>;
}
