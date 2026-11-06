import Link from "next/link";
import { FlaskConical, History, Play, Plus, Rocket } from "lucide-react";

import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { createExperimentAction, runExperimentAction } from "@/lib/actions";
import {
  getDatasets,
  getExperimentRun,
  getExperimentRuns,
  getExperiments,
  getRubrics,
  hasAuthToken,
  resolveProject,
} from "@/lib/api";
import type { ExperimentRun } from "@/lib/types";

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
  if (!iso) return "—";
  const diff = Date.now() - Date.parse(iso);
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "agora";
  if (mins < 60) return `${mins}m atrás`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h atrás`;
  return `${Math.floor(hrs / 24)}d atrás`;
}

function RunResultCard({ run }: { run: ExperimentRun }) {
  const variants = Object.entries(run.by_variant);
  const baselineScore = variants[0]?.[1]?.avg_score ?? 0;

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div className="card__header">
        <div>
          <h3 className="card__title">Resultado da run</h3>
          <div className="card__subtitle">
            {relTime(run.completed_at ?? run.created_at)} · {variants.length} variantes
          </div>
        </div>
        <span
          className={`badge ${run.passed ? "badge--ok" : "badge--err"}`}
        >
          <span className="badge__dot" />
          {run.passed ? "Aprovado (simulado)" : "Falhou (simulado)"}
        </span>
      </div>
      <div className="card__body card__body--flush">
        <table className="t">
          <thead>
            <tr>
              <th>Variante</th>
              <th>Score</th>
              <th>Custo / call</th>
              <th>p95 latência</th>
              <th>Δ baseline</th>
              <th>Status</th>
              <th style={{ width: 32 }} />
            </tr>
          </thead>
          <tbody>
            {variants.map(([name, metrics], i) => {
              const isBaseline = i === 0;
              const delta = metrics.avg_score - baselineScore;
              const isWinner =
                !isBaseline &&
                metrics.avg_score ===
                  Math.max(...variants.map(([, m]) => m.avg_score));
              return (
                <tr
                  key={name}
                  style={
                    isWinner ? { background: "rgba(34,211,168,0.06)" } : undefined
                  }
                >
                  <td>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      {isWinner && (
                        <Rocket size={14} style={{ color: "var(--ok)", flexShrink: 0 }} />
                      )}
                      <span className="t__name">{name}</span>
                    </div>
                  </td>
                  <td>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <div
                        style={{
                          width: 80,
                          height: 6,
                          background: "var(--bg-2)",
                          borderRadius: 3,
                          overflow: "hidden",
                        }}
                      >
                        <div
                          style={{
                            width: `${metrics.avg_score * 100}%`,
                            height: "100%",
                            background: isWinner ? "var(--ok)" : "var(--accent)",
                          }}
                        />
                      </div>
                      <span
                        style={{
                          fontFamily: "var(--font-mono)",
                          fontSize: 13,
                          color: isWinner ? "var(--ok)" : "var(--text-dim)",
                        }}
                      >
                        {metrics.avg_score.toFixed(2)}
                      </span>
                    </div>
                  </td>
                  <td className="t__num">
                    ${metrics.avg_cost_usd_per_item.toFixed(5)}
                  </td>
                  <td className="t__num">
                    {metrics.avg_latency_ms.toFixed(0)}ms
                  </td>
                  <td>
                    {isBaseline ? (
                      <span className="t__faint" style={{ fontSize: 12 }}>
                        baseline
                      </span>
                    ) : (
                      <span
                        style={{
                          fontFamily: "var(--font-mono)",
                          fontSize: 12,
                          color: delta >= 0 ? "var(--ok)" : "var(--err)",
                        }}
                      >
                        {delta >= 0 ? "+" : ""}
                        {(delta * 100).toFixed(1)}pp
                      </span>
                    )}
                  </td>
                  <td>
                    {isWinner ? (
                      <span className="badge badge--ok">
                        <span className="badge__dot" /> winner
                      </span>
                    ) : (
                      <span className="badge">
                        <span className="badge__dot" /> avaliada
                      </span>
                    )}
                  </td>
                  <td />
                </tr>
              );
            })}
          </tbody>
        </table>
        {run.criteria_failures.length > 0 && (
          <div
            style={{
              padding: "10px 16px",
              borderTop: "1px solid var(--border-subtle)",
              fontSize: 12,
              color: "var(--err)",
              fontFamily: "var(--font-mono)",
            }}
          >
            Falhas nos critérios: {run.criteria_failures.join(", ")}
          </div>
        )}
      </div>
    </div>
  );
}

const RUN_STATUS_LABEL: Record<string, string> = {
  completed: "concluída",
  error: "erro",
  running: "rodando",
};

function RunHistoryCard({
  runs,
  experimentName,
  activeRunId,
}: {
  runs: ExperimentRun[];
  experimentName: string;
  activeRunId?: string;
}) {
  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div className="card__header">
        <div>
          <h3 className="card__title">Histórico</h3>
          <div className="card__subtitle">
            {experimentName} · {runs.length} runs recentes
          </div>
        </div>
      </div>
      <div className="card__body card__body--flush">
        {runs.length === 0 ? (
          <p className="t__faint" style={{ padding: "16px", fontSize: 13 }}>
            Nenhuma run ainda. Use “Rodar” na lista de experimentos para gerar a primeira.
          </p>
        ) : (
          <table className="t">
            <thead>
              <tr>
                <th>Quando</th>
                <th>Status</th>
                <th>Resultado</th>
                <th>Variantes</th>
                <th>Melhor score</th>
                <th>Custo total</th>
                <th>Falhas</th>
                <th style={{ width: 80 }} />
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => {
                const metrics = Object.values(run.by_variant);
                const best = metrics.length ? Math.max(...metrics.map((m) => m.avg_score)) : null;
                const cost = metrics.reduce((acc, m) => acc + m.total_cost_usd, 0);
                return (
                  <tr
                    key={run.id}
                    style={
                      run.id === activeRunId ? { background: "rgba(34,211,168,0.06)" } : undefined
                    }
                  >
                    <td className="t__muted" style={{ fontSize: 12 }}>
                      {relTime(run.completed_at ?? run.created_at)}
                    </td>
                    <td>
                      <span className="mono t__muted" style={{ fontSize: 12 }}>
                        {RUN_STATUS_LABEL[run.status] ?? run.status}
                      </span>
                    </td>
                    <td>
                      {run.passed === null ? (
                        <span className="t__faint">—</span>
                      ) : (
                        <span className={`badge ${run.passed ? "badge--ok" : "badge--err"}`}>
                          <span className="badge__dot" />
                          {run.passed ? "Aprovado" : "Falhou"}
                        </span>
                      )}
                    </td>
                    <td className="t__num">{metrics.length}</td>
                    <td className="t__num">{best === null ? "—" : best.toFixed(2)}</td>
                    <td className="t__num">${cost.toFixed(5)}</td>
                    <td className="t__num">{run.criteria_failures.length}</td>
                    <td>
                      <Link
                        href={`?experiment_id=${run.experiment_id}&run_id=${run.id}`}
                        className="btn btn--sm"
                      >
                        Ver
                      </Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

export default async function ExperimentosPage({ params, searchParams }: Props) {
  const { org, project } = await params;
  const qp = await searchParams;

  if (!(await hasAuthToken())) {
    return <AuthRequiredPanel layout="main" />;
  }

  const resolved = await resolveProject(org, project);
  const [datasetsRes, rubricsRes, experimentsRes] = await Promise.all([
    getDatasets(resolved.project_id),
    getRubrics(resolved.project_id),
    getExperiments(resolved.project_id),
  ]);

  let runDetail: Awaited<ReturnType<typeof getExperimentRun>> | null = null;
  if (qp.run_id && qp.experiment_id) {
    try {
      runDetail = await getExperimentRun(qp.experiment_id, qp.run_id);
    } catch {
      runDetail = null;
    }
  }

  let runHistory: ExperimentRun[] | null = null;
  if (qp.experiment_id) {
    try {
      runHistory = (await getExperimentRuns(qp.experiment_id)).data;
    } catch {
      runHistory = null;
    }
  }

  const experiments = experimentsRes.data;
  const historyExperiment = experiments.find((exp) => exp.id === qp.experiment_id);

  const totalVariants = experiments.reduce((acc, exp) => acc + exp.variants.length, 0);
  const withBaseline = experiments.filter((exp) => exp.baseline_variant !== null).length;
  const latestActivity = experiments.reduce<string | null>((acc, exp) => {
    if (!acc || Date.parse(exp.created_at) > Date.parse(acc)) return exp.created_at;
    return acc;
  }, null);

  return (
    <div className="page">
      {/* Header */}
      <div className="page-header">
        <div>
          <p className="page-header__eyebrow">Operação · Experimentos</p>
          <h1 className="page-header__title">Experimentos</h1>
          <p className="page-header__subtitle">
            Simulação de variantes de prompt sobre datasets, com critérios de aprovação por rubrica.
          </p>
        </div>
        <div className="row">
          <Link href="#create-experiment" className="btn btn--sm btn--primary">
            <Plus size={13} /> Novo experimento
          </Link>
        </div>
      </div>

      <div
        role="note"
        style={{
          padding: "10px 14px",
          background: "var(--warning-soft)",
          border: "1px solid var(--warning-border)",
          borderRadius: 6,
          color: "var(--warning)",
          fontSize: 13,
          marginBottom: 12,
        }}
      >
        Resultados simulados: nenhum modelo é chamado. A saída de cada variante é o prompt renderizado, então estas
        notas não medem o seu agente. Para medir respostas reais, envie traces e use Avaliações.
      </div>

      {/* Flash */}
      {qp.error && (
        <div
          style={{
            padding: "10px 14px",
            background: "var(--err-bg)",
            border: "1px solid var(--err-border)",
            borderRadius: 6,
            color: "var(--err)",
            fontSize: 13,
            marginBottom: 12,
          }}
        >
          {qp.error}
        </div>
      )}
      {(qp.created || qp.run) && (
        <div
          style={{
            padding: "10px 14px",
            background: "var(--ok-bg)",
            border: "1px solid var(--ok-border)",
            borderRadius: 6,
            color: "var(--ok)",
            fontSize: 13,
            marginBottom: 12,
          }}
        >
          {qp.created ? "Experimento criado com sucesso." : "Run executada com sucesso."}
        </div>
      )}

      {/* Summary row — só dados reais do payload */}
      <section className="module-summary" aria-label="Resumo de experimentos">
        <div className="summary-card">
          <p className="summary-card__label">Experimentos</p>
          <div className="summary-card__value">{experiments.length.toLocaleString("pt-BR")}</div>
          <div className="summary-card__hint">total no projeto</div>
        </div>
        <div className="summary-card">
          <p className="summary-card__label">Variantes</p>
          <div className="summary-card__value">{totalVariants.toLocaleString("pt-BR")}</div>
          <div className="summary-card__hint">soma das variantes</div>
        </div>
        <div className="summary-card">
          <p className="summary-card__label">Com baseline</p>
          <div className="summary-card__value">{withBaseline.toLocaleString("pt-BR")}</div>
          <div className="summary-card__hint">baseline configurado</div>
        </div>
        <div className="summary-card">
          <p className="summary-card__label">Última atividade</p>
          <div className="summary-card__value">
            {latestActivity ? relTime(latestActivity) : "—"}
          </div>
          <div className="summary-card__hint">experimento criado</div>
        </div>
      </section>

      {/* Run result */}
      {runDetail?.run && <RunResultCard run={runDetail.run} />}

      {/* Run history */}
      {runHistory && (
        <RunHistoryCard
          runs={runHistory}
          experimentName={historyExperiment?.name ?? qp.experiment_id ?? ""}
          activeRunId={qp.run_id}
        />
      )}

      {/* Experiments table */}
      {experiments.length === 0 ? (
        <div className="card" style={{ padding: "48px 24px", textAlign: "center" }}>
          <FlaskConical
            size={32}
            style={{ color: "var(--text-faint)", margin: "0 auto 12px" }}
          />
          <p style={{ color: "var(--text-muted)", marginBottom: 6, fontWeight: 600 }}>
            Nenhum experimento ainda
          </p>
          <p style={{ color: "var(--text-faint)", fontSize: 13, maxWidth: 400, margin: "0 auto 20px" }}>
            Crie variantes para comparar prompts, modelos ou parâmetros no mesmo dataset com critérios de aprovação por rubrica.
          </p>
          <ol
            style={{
              textAlign: "left",
              display: "inline-block",
              fontSize: 13,
              color: "var(--text-muted)",
              lineHeight: "1.8",
            }}
          >
            <li>Garanta que exista ao menos um dataset e uma rubrica.</li>
            <li>Crie variantes <code style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}>control</code> e <code style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}>candidate</code>.</li>
            <li>Rode o experimento e compare pass rate, custo e latência.</li>
          </ol>
        </div>
      ) : (
        <div className="table-wrap">
          <table className="t">
            <thead>
              <tr>
                <th>Experimento</th>
                <th>Dataset</th>
                <th>Rubrica</th>
                <th>Variantes</th>
                <th>Baseline</th>
                <th className="">Criado</th>
                <th style={{ width: 140 }} />
              </tr>
            </thead>
            <tbody>
              {experiments.map((exp) => (
                <tr key={exp.id}>
                  <td>
                    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                      <span className="t__name">{exp.name}</span>
                      <span
                        style={{
                          fontSize: 11,
                          color: "var(--text-faint)",
                          fontFamily: "var(--font-mono)",
                        }}
                      >
                        {exp.id.slice(0, 16)}…
                      </span>
                    </div>
                  </td>
                  <td>
                    <span className="mono t__muted" style={{ fontSize: 12 }}>
                      {exp.dataset_id.slice(0, 16)}…
                    </span>
                  </td>
                  <td>
                    <span className="mono t__muted" style={{ fontSize: 12 }}>
                      {exp.rubric_id.slice(0, 16)}…
                    </span>
                  </td>
                  <td>
                    <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                      {exp.variants.map((v) => (
                        <span key={v.name} className="tag">
                          {v.name}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td>
                    <span className="mono t__muted" style={{ fontSize: 12 }}>
                      {exp.baseline_variant ?? "—"}
                    </span>
                  </td>
                  <td className="t__muted" style={{ fontSize: 12 }}>
                    {relTime(exp.created_at)}
                  </td>
                  <td>
                    <div className="row" style={{ gap: 4, justifyContent: "flex-end" }}>
                      <Link href={`?experiment_id=${exp.id}`} className="btn btn--sm">
                        <History size={12} /> Histórico
                      </Link>
                      <form action={runExperimentAction} style={{ display: "inline" }}>
                        <input type="hidden" name="org" value={org} />
                        <input type="hidden" name="project" value={project} />
                        <input type="hidden" name="experiment_id" value={exp.id} />
                        <button type="submit" className="btn btn--sm">
                          <Play size={12} /> Rodar
                        </button>
                      </form>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Create form (collapsible) */}
      {datasetsRes.data.length > 0 && rubricsRes.data.length > 0 && (
        <details
          id="create-experiment"
          style={{
            background: "var(--surface-1)",
            border: "1px solid var(--border)",
            borderRadius: 8,
            marginTop: 16,
          }}
        >
          <summary
            style={{
              padding: "12px 16px",
              cursor: "pointer",
              fontSize: 13,
              fontWeight: 500,
              color: "var(--text-dim)",
              listStyle: "none",
              display: "flex",
              alignItems: "center",
              gap: 8,
            }}
          >
            <Plus size={13} /> Criar novo experimento
          </summary>
          <div style={{ padding: "0 16px 20px" }}>
            <form
              action={createExperimentAction}
              style={{ display: "flex", flexDirection: "column", gap: 14, marginTop: 12 }}
            >
              <input type="hidden" name="org" value={org} />
              <input type="hidden" name="project" value={project} />
              <input type="hidden" name="project_id" value={resolved.project_id} />

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 13 }}>
                  <span style={{ color: "var(--text-muted)" }}>Nome</span>
                  <input
                    name="name"
                    placeholder="q2-model-comparison"
                    required
                    style={{
                      background: "var(--bg-2)",
                      border: "1px solid var(--border)",
                      borderRadius: 6,
                      padding: "6px 10px",
                      color: "var(--text)",
                      fontSize: 13,
                    }}
                  />
                </label>

                <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 13 }}>
                  <span style={{ color: "var(--text-muted)" }}>Variante baseline</span>
                  <input
                    name="baseline_variant"
                    defaultValue="control"
                    style={{
                      background: "var(--bg-2)",
                      border: "1px solid var(--border)",
                      borderRadius: 6,
                      padding: "6px 10px",
                      color: "var(--text)",
                      fontSize: 13,
                    }}
                  />
                </label>

                <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 13 }}>
                  <span style={{ color: "var(--text-muted)" }}>Dataset</span>
                  <select
                    name="dataset_id"
                    defaultValue={datasetsRes.data[0]?.id ?? ""}
                    required
                    style={{
                      background: "var(--bg-2)",
                      border: "1px solid var(--border)",
                      borderRadius: 6,
                      padding: "6px 10px",
                      color: "var(--text)",
                      fontSize: 13,
                    }}
                  >
                    {datasetsRes.data.map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.slug}
                      </option>
                    ))}
                  </select>
                </label>

                <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 13 }}>
                  <span style={{ color: "var(--text-muted)" }}>Rubrica</span>
                  <select
                    name="rubric_id"
                    defaultValue={rubricsRes.data[0]?.id ?? ""}
                    required
                    style={{
                      background: "var(--bg-2)",
                      border: "1px solid var(--border)",
                      borderRadius: 6,
                      padding: "6px 10px",
                      color: "var(--text)",
                      fontSize: 13,
                    }}
                  >
                    {rubricsRes.data.map((r) => (
                      <option key={r.id} value={r.id}>
                        {r.slug} (v{r.current_version})
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 13 }}>
                <span style={{ color: "var(--text-muted)" }}>Variantes JSON</span>
                <textarea
                  name="variants_json"
                  rows={6}
                  defaultValue={JSON.stringify(
                    [
                      { name: "control", model: "openai/gpt-4o-mini", params: { temperature: 0.2 } },
                      { name: "candidate", model: "openai/gpt-4.1", params: { temperature: 0.2 } },
                    ],
                    null,
                    2,
                  )}
                  style={{
                    background: "var(--bg-2)",
                    border: "1px solid var(--border)",
                    borderRadius: 6,
                    padding: "8px 10px",
                    color: "var(--text)",
                    fontSize: 12,
                    fontFamily: "var(--font-mono)",
                    resize: "vertical",
                  }}
                />
              </label>

              <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 13 }}>
                <span style={{ color: "var(--text-muted)" }}>Critérios de aprovação JSON</span>
                <textarea
                  name="pass_criteria_json"
                  rows={4}
                  defaultValue={JSON.stringify(
                    { min_pass_rate: 0.7, no_regression_vs: "control", no_regression_delta: 0.02 },
                    null,
                    2,
                  )}
                  style={{
                    background: "var(--bg-2)",
                    border: "1px solid var(--border)",
                    borderRadius: 6,
                    padding: "8px 10px",
                    color: "var(--text)",
                    fontSize: 12,
                    fontFamily: "var(--font-mono)",
                    resize: "vertical",
                  }}
                />
              </label>

              <div>
                <button type="submit" className="btn btn--primary">
                  <FlaskConical size={13} /> Criar experimento
                </button>
              </div>
            </form>
          </div>
        </details>
      )}

      {/* No datasets/rubrics warning */}
      {(datasetsRes.data.length === 0 || rubricsRes.data.length === 0) && (
        <div
          style={{
            marginTop: 16,
            padding: "12px 16px",
            background: "var(--warn-bg)",
            border: "1px solid var(--warn-border)",
            borderRadius: 8,
            fontSize: 13,
            color: "var(--warn)",
          }}
        >
          {datasetsRes.data.length === 0
            ? "Crie ao menos um dataset antes de criar um experimento."
            : "Crie ao menos uma rubrica antes de criar um experimento."}
        </div>
      )}

    </div>
  );
}
