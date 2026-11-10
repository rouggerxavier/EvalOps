import Link from "next/link";
import { taskRead } from "@/lib/api";
import type { ExecutionBudget, ImportedExecution } from "@/lib/execution-types";
import { PlanForm } from "../plans/PlanForm";
const statuses: Record<string, string> = { queued: "Na fila", running: "Em execução", cancelled: "Cancelada", succeeded: "Concluída", failed: "Falhou", uncertain: "Incerta", timed_out: "Tempo esgotado" };
export async function ControlledResult({ result, org, project, canCancel }: { result: ImportedExecution; org: string; project: string; canCancel: boolean }) {
  const budget = await taskRead<ExecutionBudget>(`/executions/${encodeURIComponent(result.id)}/budget`);
  return <div className="page ops-page"><header className="ops-page-header"><div><h1>Execução controlada</h1><p style={{ overflowWrap: "anywhere" }}>{result.id} · {result.environment}</p></div><Link href={`/o/${org}/p/${project}/evaluations/executions`}>Execuções</Link></header>
    <section className="card"><h2>{statuses[result.status] ?? result.status}</h2><p>Estado técnico não aprova qualidade. Reserva não significa gasto.</p>{result.control && <Link href={`/o/${org}/p/${project}/evaluations/executions/plans/${result.control.plan_id}`}>Plano selado</Link>}<p style={{ overflowWrap: "anywhere" }}>Manifest: {result.manifest_hash}</p>{result.control?.cancel_requested_at && <p>Cancelamento solicitado em {result.control.cancel_requested_at}.</p>}{canCancel && ["queued", "running"].includes(result.status) && <PlanForm org={org} project={project} id={result.id} intent="cancel" />}</section>
    <section className="card"><h2>Orçamento em USD</h2><dl><dt>Teto reservado</dt><dd><data value={budget.reserved_limit_usd}>{budget.reserved_limit_usd}</data></dd><dt>Reserva ainda retida</dt><dd><data value={budget.held_usd}>{budget.held_usd}</data></dd><dt>Gasto conhecido</dt><dd>{budget.known_spent_usd ?? "Ainda não conhecido"}</dd><dt>Slots retidos</dt><dd>{budget.slots_active ? "Sim" : "Não"}</dd></dl><p>Gasto desconhecido mantém reserva e não autoriza repetição automática.</p></section>
    <section className="card"><h2>Ledger</h2><div className="table-wrap"><table className="t"><thead><tr><th>Evento</th><th>USD</th><th>Fonte</th><th>Versão</th></tr></thead><tbody>{budget.entries.map(entry => <tr key={entry.id}><td>{entry.kind}</td><td>{entry.amount_usd}</td><td>{entry.measurement_source}</td><td>{entry.pricing_version}</td></tr>)}</tbody></table></div></section>
  </div>;
}
