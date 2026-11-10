import Link from "next/link";
import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { hasAuthToken, resolveProject, taskRead } from "@/lib/api";
import type { CuratedCase } from "@/lib/investigation-types";
import type { TraceDetailResponse } from "@/lib/types";
import { CaseForm, ClassificationForm } from "./CaseForm";
export default async function CasesPage({ params, searchParams }: { params: Promise<{ org: string; project: string; id: string }>; searchParams: Promise<{ item?: string; trace?: string }> }) {
  if (!(await hasAuthToken())) return <AuthRequiredPanel layout="main" />;
  const { org, project, id } = await params;
  const query = await searchParams;
  const resolved = await resolveProject(org, project);
  const dataset = await taskRead<{ id: string; slug: string; project_id: string; access_label: { allowed_environments: string[] } | null }>(`/datasets/${encodeURIComponent(id)}`);
  if (dataset.project_id !== resolved.project_id) throw new Error("Dataset não pertence ao projeto.");
  const capabilities = await taskRead<{ permissions: string[] }>(`/projects/${resolved.project_id}/capabilities`);
  const { data } = await taskRead<{ data: CuratedCase[] }>(`/datasets/${encodeURIComponent(id)}/cases`);
  const selected = query.item ? await taskRead<CuratedCase>(`/datasets/${encodeURIComponent(id)}/items/${encodeURIComponent(query.item)}`) : undefined;
  let trace: { id: string; input: Record<string, unknown>; output: string } | undefined;
  if (query.trace) {
    const evidence = await taskRead<TraceDetailResponse & { observed_output: string }>(`/task-evidence/traces/${encodeURIComponent(query.trace)}`);
    if (evidence.trace.project_id !== resolved.project_id) throw new Error("Trace não pertence ao projeto.");
    trace = { id: evidence.trace.id, input: { messages: evidence.spans.find(span => span.messages_in?.length)?.messages_in ?? [] }, output: evidence.observed_output };
  }
  const base = `/o/${org}/p/${project}/datasets/${id}/cases`;
  return <div className="page ops-page"><header className="ops-page-header"><h1>Curadoria de {dataset.slug}</h1><Link href={`/o/${org}/p/${project}/datasets`}>Datasets</Link></header>
    {!dataset.access_label && <section className="card"><h2>Origem ainda não classificada</h2>{capabilities.permissions.includes("admin") ? <ClassificationForm org={org} project={project} dataset={id} trace={query.trace} /> : <p>Um owner precisa classificar a origem antes do acesso por automação.</p>}</section>}
    <section className="card"><h2>Casos</h2><div className="table-wrap"><table className="t"><thead><tr><th>Amostra</th><th>Referência</th><th>Revisão</th></tr></thead><tbody>{data.map(row => <tr key={row.id}><td><Link href={`${base}?item=${row.id}`}>{row.sample_id}</Link></td><td>{row.reference_status === "reviewed" ? "Revisada por humano" : row.reference_status === "rejected" ? "Rejeitada" : "Rascunho"}</td><td>{row.revision}</td></tr>)}</tbody></table></div>{!data.length && <p>Nenhum caso salvo.</p>}</section>
    {trace && <section className="card"><h2>Saída observada</h2><p>Esta resposta é evidência do modelo e não uma referência validada.</p><pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{trace.output || "Sem saída observada."}</pre></section>}
    {capabilities.permissions.includes("write") && dataset.access_label && <section className="card"><h2>{selected ? "Revisar caso" : "Novo caso"}</h2><CaseForm key={`${selected?.id ?? "new"}-${selected?.revision ?? 0}`} org={org} project={project} dataset={id} current={selected} trace={trace} environment={dataset.access_label.allowed_environments[0]} /></section>}
  </div>;
}
