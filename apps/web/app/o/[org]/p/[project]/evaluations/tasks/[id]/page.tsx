import Link from "next/link";
import { ClassificationResult } from "./ClassificationResult";
import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { hasAuthToken, resolveProject, taskRead } from "@/lib/api";
import { taskDecisionLabels } from "@/lib/task-types";
import type { TaskEvaluation, MetricFact } from "@/lib/task-types";

export default async function TaskResultPage({ params, searchParams }: { params: Promise<{ org: string; project: string; id: string }>; searchParams: Promise<{ cursor?: string }> }) {
  if (!(await hasAuthToken())) return <AuthRequiredPanel layout="main" />;
  const { org, project, id } = await params;
  const resolved = await resolveProject(org, project);
  const result = await taskRead<TaskEvaluation>(`/task-evaluations/${encodeURIComponent(id)}`);
  if (result.project_id !== resolved.project_id) throw new Error("Avaliação não pertence ao projeto.");
  const { data: metrics } = await taskRead<{ data: MetricFact[] }>(`/task-evaluations/${encodeURIComponent(id)}/metrics`);
  const snapshot = await taskRead<{ dataset_id: string }>(`/dataset-snapshots/${result.snapshot_id}`);
  if (result.evaluator_manifest.id === "classification.standard") return <ClassificationResult result={result} metrics={metrics} org={org} project={project} dataset={snapshot.dataset_id} />;
  const scalars = metrics.filter(fact => fact.value_type === "scalar");
  const residual = metrics.find(fact => fact.definition_id === "regression.residuals" && fact.scope === "dataset");
  const points = residual?.value && typeof residual.value === "object" && "points" in residual.value ? residual.value.points : [];
  const histogram = metrics.find(fact => fact.definition_id === "regression.residual_histogram" && fact.scope === "dataset");
  const bins = histogram?.value && typeof histogram.value === "object" && "cells" in histogram.value ? histogram.value : null;
  const query = await searchParams;
  const requestedCursor = Number(query.cursor ?? 0);
  const cursor = Number.isSafeInteger(requestedCursor) && requestedCursor >= 0 ? requestedCursor : 0;
  const measured = points.filter(point => point.y !== null);
  const xMin = measured.length ? Math.min(...measured.map(point => point.x)) : 0;
  const xMax = measured.length ? Math.max(...measured.map(point => point.x)) : 1;
  const yMin = measured.length ? Math.min(...measured.map(point => point.y!)) : 0;
  const yMax = measured.length ? Math.max(...measured.map(point => point.y!)) : 1;
  const largest = await taskRead<{ data: { sample_id: string; residual: { y: number | null } | null }[] }>(`/task-evaluations/${encodeURIComponent(id)}/samples?order=absolute_error_desc&limit=10`);
  return <div className="page ops-page"><header className="ops-page-header"><div><h1>Resultado de regressão</h1><p>{result.id} · {result.environment} · {result.status}</p></div><Link href={`/o/${org}/p/${project}/evaluations/tasks`}>Todas as tarefas</Link></header>
    <section className="card"><h2>{result.decision ? taskDecisionLabels[result.decision] : "Aguardando decisão"}</h2><p>{result.decision_reasons.includes("no_quality_policy") ? "Sem política de qualidade. As métricas abaixo não representam aprovação ou reprovação." : result.decision_reasons.join(", ")}</p><p>Cobertura: {result.n_valid}/{result.n_total}. Avaliador: {result.evaluator_manifest.id}@{result.evaluator_manifest.version}.</p><p>Snapshot: <code style={{ overflowWrap: "anywhere" }}>{result.snapshot_id}</code></p><Link href={`/o/${org}/p/${project}/datasets/${snapshot.dataset_id}/cases`}>Revisar casos do dataset</Link></section>
    <section className="card"><h2>Métricas</h2><div className="table-wrap"><table className="t"><thead><tr><th>Métrica</th><th>Grupo</th><th>Valor</th><th>Unidade</th><th>Validade / motivo</th><th>Pares válidos</th></tr></thead><tbody>{scalars.map(fact => <tr key={fact.id}><td>{fact.definition_id}</td><td>{fact.scope_key}</td><td>{typeof fact.value === "number" ? <data value={fact.value}>{fact.value.toLocaleString("pt-BR", { maximumSignificantDigits: 15 })}</data> : "Sem valor"}</td><td>{fact.unit}</td><td>{fact.state}{fact.reason ? ` / ${fact.reason}` : ""}</td><td>{fact.n_valid}/{fact.n_total}</td></tr>)}</tbody></table></div></section>
    <section className="card"><h2>Resíduos vs predição</h2>
      {measured.length > 0 ? <svg viewBox="0 0 600 240" width="100%" role="img" aria-label={`Resíduos vs predição em ${residual?.unit}; ${Math.min(measured.length, 1000)} pontos exibidos`}>
        <line x1="30" y1="210" x2="580" y2="210" stroke="currentColor" /><line x1="30" y1="20" x2="30" y2="210" stroke="currentColor" />
        {measured.slice(0, 1000).map(point => <circle key={point.key} cx={30 + ((point.x - xMin) / (xMax - xMin || 1)) * 550} cy={210 - ((point.y! - yMin) / (yMax - yMin || 1)) * 190} r="3" fill="#1D2F6F"><title>{point.key}: predição {point.x}, resíduo {point.y}</title></circle>)}
        <text x="280" y="235" fontSize="12">Predição ({residual?.unit})</text>
      </svg> : <p>Sem pontos medidos.</p>}
      {measured.length > 1000 && <p>Gráfico limitado aos primeiros 1.000 pontos. A tabela paginada abaixo permite consultar todos.</p>}
    </section>
    <section className="card"><h2>Histograma de resíduos</h2>{bins ? <div className="table-wrap"><table className="t"><thead><tr><th>Intervalo ({residual?.unit})</th><th>Amostras</th></tr></thead><tbody>{bins.row_axis.labels.map((label, index) => <tr key={label}><td>{label}</td><td>{bins.cells[index][0]}</td></tr>)}</tbody></table></div> : <p>{histogram?.reason ?? "Sem dados."}</p>}</section>
    <section className="card"><h2>Maiores erros</h2><div className="table-wrap"><table className="t"><thead><tr><th>Amostra</th><th>Resíduo ({residual?.unit})</th></tr></thead><tbody>{largest.data.map(sample => <tr key={sample.sample_id}><td>{sample.sample_id}</td><td>{sample.residual?.y ?? "Sem valor"}</td></tr>)}</tbody></table></div></section>
    <section className="card"><h2>Resíduos por amostra</h2><p>Resíduo = predição − referência. A tabela apresenta os valores calculados pela API.</p><div className="table-wrap"><table className="t"><thead><tr><th>Amostra</th><th>Predição</th><th>Resíduo ({residual?.unit})</th><th>Validade</th></tr></thead><tbody>{points.slice(cursor, cursor + 100).map(point => <tr key={point.key}><td>{point.key}</td><td>{point.x}</td><td>{point.y ?? "Sem valor"}</td><td>{point.reason ?? point.state}</td></tr>)}</tbody></table></div>{!points.length && <p>{residual?.reason ?? "Sem resíduos medidos."}</p>}
      {cursor > 0 && <Link href={`?cursor=${Math.max(0, cursor - 100)}`}>Amostras anteriores</Link>}
      {cursor + 100 < points.length && <Link href={`?cursor=${cursor + 100}`}>Próximas amostras</Link>}
    </section>
  </div>;
}
