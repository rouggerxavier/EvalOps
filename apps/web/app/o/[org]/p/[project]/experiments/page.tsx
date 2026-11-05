import Link from "next/link";
import { Play } from "lucide-react";

import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { createExperimentAction, runExperimentAction } from "@/lib/actions";
import {
  getDatasets,
  getExperimentRun,
  getExperiments,
  getRubrics,
  hasAuthToken,
  resolveProject,
} from "@/lib/api";
import type { Experiment, ExperimentRun } from "@/lib/types";
import { safeErrorMessage } from "@/lib/safe-error";

type Props = {
  params: Promise<{ org: string; project: string }>;
  searchParams: Promise<{
    created?: string;
    run?: string;
    run_id?: string;
    experiment_id?: string;
    error?: string;
  }>;
};

function relTime(iso: string | null): string {
  if (!iso) return "Sem dados";
  const minutes = Math.floor((Date.now() - Date.parse(iso)) / 60_000);
  if (minutes < 1) return "agora";
  if (minutes < 60) return `${minutes} min atrás`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} h atrás`;
  return `${Math.floor(hours / 24)} d atrás`;
}

function runBaseline(run: ExperimentRun, experiment: Experiment | undefined): string | null {
  const fromRun = run.run_metadata.baseline_variant;
  if (typeof fromRun === "string") return fromRun;
  return experiment?.baseline_variant ?? Object.keys(run.by_variant)[0] ?? null;
}

function formatScore(value: number): string {
  return value.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function ExperimentRunCard({
  run,
  experiment,
  org,
  project,
}: {
  run: ExperimentRun;
  experiment: Experiment | undefined;
  org: string;
  project: string;
}) {
  const variants = Object.entries(run.by_variant);
  const baselineName = runBaseline(run, experiment);
  const baseline = variants.find(([name]) => name === baselineName)?.[1];
  const highestScore = Math.max(...variants.map(([, metrics]) => metrics.avg_score));
  const highestVariant = variants.find(([, metrics]) => metrics.avg_score === highestScore);
  const runIsSynthetic = run.run_metadata.synthetic === true;
  const runStatus = run.passed === true ? "Aprovado" : run.passed === false ? "Não aprovado" : "Sem dados";

  return (
    <section className="card">
      <div className="card__header">
        <div>
          <h2 className="card__title">
            {highestVariant ? `Maior score: ${highestVariant[0]} (${formatScore(highestVariant[1].avg_score)})` : "Sem dados de variantes"}
          </h2>
          <p className="card__subtitle">
            {experiment?.name ?? "Execução"} · {variants.length} variantes · terminou {relTime(run.completed_at ?? run.created_at)}
          </p>
        </div>
        <span className={`badge ${run.passed === true ? "badge--ok" : run.passed === false ? "badge--err" : ""}`}>
          {runStatus}
        </span>
        {experiment ? (
          <form action={runExperimentAction}>
            <input type="hidden" name="org" value={org} />
            <input type="hidden" name="project" value={project} />
            <input type="hidden" name="experiment_id" value={experiment.id} />
            <button type="submit" className="btn">Rodar de novo</button>
          </form>
        ) : null}
      </div>
      {runIsSynthetic ? (
        <p className="ops-note">
          A resposta da variante é sintetizada. Um avaliador `llm_judge` ainda pode chamar um modelo e consumir orçamento.
        </p>
      ) : null}
      <div className="table-wrap">
        <table className="t">
          <thead>
            <tr>
              <th>Resultado</th>
              <th>Variante</th>
              <th className="t__num">Score</th>
              <th className="t__num">Custo médio por item</th>
              <th className="t__num">Latência p95</th>
              <th className="t__num">Em relação à referência</th>
            </tr>
          </thead>
          <tbody>
            {variants.length === 0 ? (
              <tr><td className="empty-row" colSpan={6}>Sem dados de variantes nesta execução.</td></tr>
            ) : variants.map(([name, metrics]) => {
              const variant = experiment?.variants.find((item) => item.name === name);
              const isBaseline = name === baselineName;
              const scoreDelta = baseline ? metrics.avg_score - baseline.avg_score : null;
              const costDelta = baseline ? metrics.avg_cost_usd_per_item - baseline.avg_cost_usd_per_item : null;
              const costText = costDelta === null || !baseline || baseline.avg_cost_usd_per_item === 0
                ? "Sem dados"
                : `${Math.round((costDelta / baseline.avg_cost_usd_per_item) * 100).toLocaleString("pt-BR")}% custo`;
              const scoreText = scoreDelta === null
                ? "Sem dados"
                : `${scoreDelta >= 0 ? "+" : ""}${(scoreDelta * 100).toFixed(1).replace(".", ",")} pp score`;

              return (
                <tr key={name}>
                  <td>
                    <span className={`badge ${isBaseline ? "" : metrics.avg_score === highestScore ? "badge--ok" : ""}`}>
                      {isBaseline ? "Referência" : metrics.avg_score === highestScore ? "Maior score" : "Comparada"}
                    </span>
                  </td>
                  <td>
                    <strong>{name}</strong>
                    <div className="t__muted">
                      {variant
                        ? [variant.prompt_version_ref, variant.model].filter(Boolean).join(", ") || "Sem dados"
                        : "Sem dados"}
                    </div>
                  </td>
                  <td className="t__num">{formatScore(metrics.avg_score)}</td>
                  <td className="t__num">US$ {metrics.avg_cost_usd_per_item.toFixed(3)}</td>
                  <td className="t__num">
                    Sem dados
                    <div className="t__muted">Média: {metrics.avg_latency_ms} ms</div>
                  </td>
                  <td className="t__num">{isBaseline ? "—" : `${costText} · ${scoreText}`}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="ops-note">Latência p95: Sem dados. A média está disponível; o custo é a média por item.</p>
    </section>
  );
}

export default async function ExperimentosPage({ params, searchParams }: Props) {
  const { org, project } = await params;
  const qp = await searchParams;

  if (!(await hasAuthToken())) return <AuthRequiredPanel layout="main" />;

  const resolved = await resolveProject(org, project);
  const [datasetsRes, rubricsRes, experimentsRes] = await Promise.all([
    getDatasets(resolved.project_id),
    getRubrics(resolved.project_id),
    getExperiments(resolved.project_id),
  ]);

  let runDetail: { run: ExperimentRun } | null = null;
  let runError = false;
  if (qp.run_id && qp.experiment_id) {
    try {
      runDetail = await getExperimentRun(qp.experiment_id, qp.run_id);
    } catch {
      runError = true;
    }
  }

  const experiments = experimentsRes.data;
  const experimentForRun = experiments.find((experiment) => experiment.id === qp.experiment_id);
  const datasetName = new Map(datasetsRes.data.map((dataset) => [dataset.id, dataset.slug]));
  const rubricName = new Map(rubricsRes.data.map((rubric) => [rubric.id, rubric.slug]));
  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1 className="page-header__title">Experimentos</h1>
          <p className="page-header__subtitle">
            Teste versões de prompt e modelo no mesmo dataset, antes de publicar.
          </p>
        </div>
        <details className="ops-inline">
          <summary className="btn btn--primary">Novo experimento</summary>
          {datasetsRes.data.length > 0 && rubricsRes.data.length > 0 ? (
            <form action={createExperimentAction} className="card ops-form">
              <input type="hidden" name="org" value={org} />
              <input type="hidden" name="project" value={project} />
              <input type="hidden" name="project_id" value={resolved.project_id} />
              <label className="ops-form__field">
                <span>Nome</span>
                <input name="name" placeholder="q2-model-comparison" minLength={2} required />
              </label>
              <label className="ops-form__field">
                <span>Dataset</span>
                <select name="dataset_id" defaultValue={datasetsRes.data[0]?.id} required>
                  {datasetsRes.data.map((dataset) => <option key={dataset.id} value={dataset.id}>{dataset.slug}</option>)}
                </select>
              </label>
              <label className="ops-form__field">
                <span>Rubrica</span>
                <select name="rubric_id" defaultValue={rubricsRes.data[0]?.id} required>
                  {rubricsRes.data.map((rubric) => <option key={rubric.id} value={rubric.id}>{rubric.slug}</option>)}
                </select>
              </label>
              <label className="ops-form__field">
                <span>Referência</span>
                <input name="baseline_variant" defaultValue="control" />
              </label>
              <label className="ops-form__field">
                <span>Variantes JSON</span>
                <textarea
                  name="variants_json"
                  rows={5}
                  defaultValue={JSON.stringify([
                    { name: "control", model: "openai/gpt-4o-mini", params: { temperature: 0.2 } },
                    { name: "candidate", model: "openai/gpt-4.1", params: { temperature: 0.2 } },
                  ], null, 2)}
                  required
                />
              </label>
              <label className="ops-form__field">
                <span>Critérios JSON</span>
                <textarea
                  name="pass_criteria_json"
                  rows={3}
                  defaultValue={JSON.stringify({ min_pass_rate: 0.7, no_regression_vs: "control", no_regression_delta: 0.02 }, null, 2)}
                />
              </label>
              <p className="ops-note">A criação exige variantes. Depois de criar, use “Rodar” na tabela.</p>
              <button type="submit" className="btn btn--primary">Criar experimento</button>
            </form>
          ) : (
            <div className="card ops-form">
              <p className="ops-empty">Crie ao menos um dataset e uma rubrica antes de começar.</p>
              {datasetsRes.data.length === 0 ? <Link href={`/o/${org}/p/${project}/datasets`}>Criar dataset</Link> : null}
              {rubricsRes.data.length === 0 ? <Link href={`/o/${org}/p/${project}/rubrics`}>Criar rubrica</Link> : null}
            </div>
          )}
        </details>
      </header>

      <p className="ops-note">
        As respostas das variantes são sintetizadas a partir do prompt. Um avaliador `llm_judge` pode chamar um modelo; esta execução não mede respostas reais do agente.
      </p>
      {qp.error ? <p className="ops-note" role="alert">{safeErrorMessage(qp.error, "Falha ao executar ação.")}</p> : null}
      {qp.created ? <p className="ops-note" role="status">Experimento criado.</p> : null}
      {qp.run ? <p className="ops-note" role="status">Execução concluída.</p> : null}

      {runDetail ? (
        <ExperimentRunCard
          run={runDetail.run}
          experiment={experimentForRun}
          org={org}
          project={project}
        />
      ) : (
        <section className="card ops-empty">
          <div>
            <h2>Resultado mais recente</h2>
            <p role={runError ? "alert" : undefined}>
              {runError
                ? "Não foi possível carregar esta execução. Sem dados do resultado."
                : "Sem dados. A API só retorna uma execução quando o ID é conhecido. Rode um experimento para ver o resultado."}
            </p>
          </div>
        </section>
      )}

      <section className="card">
        <div className="card__header"><h2 className="card__title">Todos os experimentos</h2></div>
        <div className="table-wrap">
          <table className="t">
            <thead>
              <tr>
                <th>Experimento</th>
                <th>Dataset</th>
                <th>Rubrica</th>
                <th className="t__num">Variantes</th>
                <th>Referência</th>
                <th className="t__num">Criado</th>
                <th>Ações</th>
              </tr>
            </thead>
            <tbody>
              {experiments.length === 0 ? (
                <tr><td className="empty-row" colSpan={7}>Sem dados. Crie um experimento para comparar variantes.</td></tr>
              ) : experiments.map((experiment) => (
                <tr key={experiment.id}>
                  <td><span className="t__name">{experiment.name}</span></td>
                  <td>{datasetName.get(experiment.dataset_id) ?? "Sem dados"}</td>
                  <td>{rubricName.get(experiment.rubric_id) ?? "Sem dados"}</td>
                  <td className="t__num">{experiment.variants.length}</td>
                  <td>{experiment.baseline_variant ?? experiment.variants[0]?.name ?? "Sem dados"}</td>
                  <td className="t__num">{relTime(experiment.created_at)}</td>
                  <td>
                    <form action={runExperimentAction}>
                      <input type="hidden" name="org" value={org} />
                      <input type="hidden" name="project" value={project} />
                      <input type="hidden" name="experiment_id" value={experiment.id} />
                      <button type="submit" className="btn btn--sm"><Play size={12} aria-hidden="true" /> Rodar</button>
                    </form>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
