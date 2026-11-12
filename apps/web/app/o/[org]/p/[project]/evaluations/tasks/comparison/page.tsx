import Link from "next/link";
import { resolveProject, taskRead, hasAuthToken } from "@/lib/api";
import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";

type Run = { id: string; project_id: string; decision: string; decision_reasons: string[]; policy_hash: string; policy_timing: string; n_pairs: number; manifest: { min_pairs: number; required_coverage: number; max_degradation: number };
  candidates: { evaluation_id: string; baseline_value: number | null; candidate_value: number | null; unit: string; delta: number | null; decision: string; reasons: string[] }[] };
const reasons: Record<string, string> = { insufficient_pairs: "Pares insuficientes", insufficient_coverage: "Cobertura insuficiente", incompatible_protocol: "Protocolos incompatíveis", primary_metric_unavailable: "Métrica principal indisponível", degradation_exceeded: "Degradação acima do limite", critical_case_failed: "Caso crítico reprovado", critical_case_inconclusive: "Caso crítico inconclusivo", human_review_required: "Revisão humana necessária" };
const labels: Record<string, string> = { pass: "Aprovado pela política", fail: "Reprovado pela política", review: "Revisão necessária", inconclusive: "Inconclusivo" };
export default async function ComparisonPage({ params, searchParams }: { params: Promise<{ org: string; project: string }>; searchParams: Promise<{ experiment?: string; comparison_run?: string }> }) {
  if (!(await hasAuthToken())) return <AuthRequiredPanel layout="main" />;
  const { org, project } = await params;
  const query = await searchParams;
  if (!query.experiment || !query.comparison_run) throw new Error("Informe experimento e comparação.");
  const resolved = await resolveProject(org, project);
  const { run } = await taskRead<{ run: Run }>(`/experiments/${encodeURIComponent(query.experiment)}/runs/${encodeURIComponent(query.comparison_run)}?view=task_v1`);
  if (run.project_id !== resolved.project_id) throw new Error("Comparação não pertence ao projeto.");
  return <div className="page ops-page"><header className="ops-page-header"><h1>Comparação offline</h1><Link href={`/o/${org}/p/${project}/evaluations/tasks`}>Todas as tarefas</Link></header>
    <section className="card"><h2>{labels[run.decision]}</h2><p>{run.decision_reasons.map(reason => reasons[reason] ?? reason).join(", ")}</p><p>{run.n_pairs} pares. Mínimo da política: {run.manifest.min_pairs}; cobertura mínima: {run.manifest.required_coverage * 100}%; degradação máxima: {run.manifest.max_degradation}.</p><details><summary>Política e reprodutibilidade</summary><p>Hash: <code style={{ overflowWrap: "anywhere" }}>{run.policy_hash}</code></p><p>{run.policy_timing === "post_observation" ? "Política escolhida após observar resultados." : run.policy_timing}</p></details><p>Análise descritiva. Não implica significância estatística ou autorização de deploy.</p></section>
    <section className="card"><div className="table-wrap"><table className="t"><thead><tr><th>Candidato</th><th>Baseline pareado</th><th>Candidato pareado</th><th>Delta</th><th>Unidade</th><th>Decisão / motivos</th></tr></thead><tbody>{run.candidates.map(candidate => <tr key={candidate.evaluation_id}><td>{candidate.evaluation_id}</td><td>{candidate.baseline_value ?? "Sem valor"}</td><td>{candidate.candidate_value ?? "Sem valor"}</td><td>{candidate.delta ?? "Sem valor"}</td><td>{candidate.unit}</td><td>{labels[candidate.decision]} · {candidate.reasons.map(reason => reasons[reason] ?? reason).join(", ")}</td></tr>)}</tbody></table></div></section>
  </div>;
}
