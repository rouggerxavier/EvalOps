import Link from "next/link";
import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { hasAuthToken, resolveProject, taskRead } from "@/lib/api";
import type { ImportedExecution } from "@/lib/execution-types";
export default async function ExecutionPage({ params }: { params: Promise<{ org: string; project: string; id: string }> }) {
  if (!(await hasAuthToken())) return <AuthRequiredPanel layout="main" />;
  const { org, project, id } = await params;
  const resolved = await resolveProject(org, project);
  const result = await taskRead<ImportedExecution>(`/executions/${encodeURIComponent(id)}`);
  if (result.project_id !== resolved.project_id) throw new Error("Execução não pertence ao projeto.");
  const base = `/o/${org}/p/${project}`;
  return <div className="page ops-page"><header className="ops-page-header"><div><h1>Captura externa de execução</h1><p style={{ overflowWrap: "anywhere" }}>{result.id} · {result.environment} · {result.mode}</p></div><Link href={`${base}/evaluations/executions`}>Todas as capturas</Link></header>
    <section className="card"><h2>Status declarado: {result.status}</h2><p>Proveniência parcial. A API verifica vínculos e integridade, mas não verifica o processo externo. Status de execução não aprova qualidade.</p><p>Limites do manifest são declarados pelo produtor. Esta importação não reserva orçamento nem autoriza repetir chamadas.</p><p style={{ overflowWrap: "anywhere" }}>Manifest: {result.manifest_hash}</p></section>
    {result.attempts.map(attempt => <section className="card" key={attempt.id}><h2>Tentativa importada {attempt.attempt_number}</h2><p>{attempt.result.exit_reason}</p><p>Captura declarada: {attempt.result.capture_status}. Início: {attempt.result.started_at}. Fim: {attempt.result.ended_at}.</p><h3>Custo reportado</h3><p>{attempt.result.cost.state === "provided" ? `USD ${attempt.result.cost.amount_usd} · ${attempt.result.cost.measurement_source}` : attempt.result.cost.state === "unknown" ? "Custo desconhecido" : "Custo não medido"}</p><p>Tarifa: {attempt.result.cost.pricing_version ?? "Não declarada"}</p><h3>Limitações da captura</h3><ul>{attempt.result.warnings.map(warning => <li key={warning}>{warning}</li>)}</ul><h3>Traces vinculados</h3><ul>{attempt.result.trace_ids.map(trace => <li key={trace}><Link href={`${base}/traces/${trace}`}>{trace}</Link></li>)}</ul><details><summary>Resultado e hashes selados</summary><pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{JSON.stringify(attempt, null, 2)}</pre></details></section>)}
    <section className="card"><h2>Manifest selado</h2><pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{JSON.stringify(result.manifest, null, 2)}</pre><Link href={`${base}/evaluations/investigations`}>Investigar esta captura</Link></section>
  </div>;
}
