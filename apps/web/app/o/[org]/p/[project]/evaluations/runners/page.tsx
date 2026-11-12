import Link from "next/link";
import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { hasAuthToken, resolveProject, taskRead } from "@/lib/api";
import { PolicyForm, RegisterForm, RunnerControls } from "./ControlForms";
export default async function RunnersPage({ params, searchParams }: { params: Promise<{ org: string; project: string }>; searchParams: Promise<{ cursor?: string }> }) {
  if (!(await hasAuthToken())) return <AuthRequiredPanel layout="main" />;
  const { org, project } = await params;
  const resolved = await resolveProject(org, project);
  const capabilities = await taskRead<{ permissions: string[] }>(`/projects/${resolved.project_id}/capabilities`);
  if (!capabilities.permissions.includes("admin")) return <div className="page ops-page"><h1>Runners externos</h1><p>Um owner precisa gerenciar política e credenciais.</p></div>;
  const budget = await taskRead<{ version: number; budget: unknown }>(`/projects/${resolved.project_id}/organization-execution-budget`);
  const policy = await taskRead<{ version: number; policy: unknown }>(`/projects/${resolved.project_id}/execution-policy`);
  const query = await searchParams;
  const requested = Number(query.cursor ?? 0);
  const cursor = Number.isSafeInteger(requested) && requested >= 0 && requested <= 2147483647 ? requested : 0;
  const { data, next_cursor } = await taskRead<{ next_cursor: number | null; data: { id: string; name: string; capabilities: unknown; disabled_at: string | null }[] }>(`/projects/${resolved.project_id}/runners?cursor=${cursor}`);
  return <div className="page ops-page"><header className="ops-page-header"><div><h1>Runners externos</h1><p>Política e registro administrativos. Dispatch continua indisponível até entrega dos controles de execução.</p></div><Link href={`/o/${org}/p/${project}/evaluations/executions`}>Capturas externas</Link></header>
    <section className="card"><h2>Budget da organização</h2><p>Teto compartilhado entre os projetos desta organização.</p><PolicyForm key={`budget-${budget.version}`} org={org} project={project} version={budget.version} policy={budget.budget} organization /></section>
    <section className="card"><h2>Política do projeto</h2><PolicyForm key={policy.version} org={org} project={project} version={policy.version} policy={policy.policy} /></section>
    <section className="card"><h2>Registrar runner</h2><RegisterForm org={org} project={project} /></section>
    {cursor > 0 && <Link href={`?cursor=${Math.max(0, cursor-100)}`}>Runners anteriores</Link>}{next_cursor !== null && <Link href={`?cursor=${next_cursor}`}>Próximos runners</Link>}
    {data.map(row => <section className="card" key={row.id}><h2>{row.name}</h2><p style={{ overflowWrap: "anywhere" }}>{row.id} · {row.disabled_at ? "Desabilitado" : "Registrado"}</p><pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{JSON.stringify(row.capabilities, null, 2)}</pre>{!row.disabled_at && <RunnerControls org={org} project={project} id={row.id} expires={new Date(Date.now()+86400000).toISOString()} />}</section>)}
  </div>;
}
