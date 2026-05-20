import Link from "next/link";
import { FlaskConical, MoreHorizontal, Play, Plus, RefreshCw, Rocket } from "lucide-react";

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
    <div className="evo-card" style={{ marginBottom: 16 }}>
      <div className="evo-card__header">
        <div>
          <h3 className="evo-card__title">Resultado da run</h3>
          <div className="evo-card__subtitle">
            {relTime(run.completed_at ?? run.created_at)} · {variants.length} variantes
          </div>
        </div>
        <span
          className={`evo-badge ${run.passed ? "evo-badge--ok" : "evo-badge--err"}`}
        >
          <span className="evo-badge__dot" />
          {run.passed ? "Aprovado" : "Falhou"}
        </span>
      </div>
      <div className="evo-card__body evo-card__body--flush">
        <table className="evo-table">
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
                      <span className="evo-table__name">{name}</span>
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
                  <td className="evo-table__num">
                    ${metrics.avg_cost_usd_per_item.toFixed(5)}
                  </td>
                  <td className="evo-table__num">
                    {metrics.avg_latency_ms.toFixed(0)}ms
                  </td>
                  <td>
                    {isBaseline ? (
                      <span className="evo-faint" style={{ fontSize: 12 }}>
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
                      <span className="evo-badge evo-badge--ok">
                        <span className="evo-badge__dot" /> winner
                      </span>
                    ) : (
                      <span className="evo-badge">
                        <span className="evo-badge__dot" /> avaliada
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

  const experiments = experimentsRes.data;

  const totalVariants = experiments.reduce((acc, exp) => acc + exp.variants.length, 0);
  const withBaseline = experiments.filter((exp) => exp.baseline_variant !== null).length;
  const latestActivity = experiments.reduce<string | null>((acc, exp) => {
    if (!acc || Date.parse(exp.created_at) > Date.parse(acc)) return exp.created_at;
    return acc;
  }, null);

  return (
    <div className="evo-page">
      {/* Header */}
      <div className="evo-page-header">
        <div>
          <p className="evo-page-header__eyebrow">Operação · Experimentos</p>
          <h1 className="evo-page-header__title">Experimentos</h1>
          <p className="evo-page-header__subtitle">
            Comparações controladas de modelos, prompts e parâmetros sobre datasets com critérios de aprovação por rubrica.
          </p>
        </div>
        <div className="evo-row">
          <button
            type="button"
            className="evo-btn evo-btn--sm"
            disabled
            data-status="planned"
            title="Exportar relatório — em breve"
            style={{ opacity: 0.5, cursor: "not-allowed" }}
          >
            <RefreshCw size={13} /> Exportar relatório
          </button>
          <Link href="#create-experiment" className="evo-btn evo-btn--sm evo-btn--primary">
            <Plus size={13} /> Novo experimento
          </Link>
        </div>
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
      <section className="evo-summary-row" aria-label="Resumo de experimentos">
        <div className="evo-summary-card">
          <p className="evo-summary-card__label">Experimentos</p>
          <div className="evo-summary-card__value">{experiments.length.toLocaleString("pt-BR")}</div>
          <div className="evo-summary-card__hint">total no projeto</div>
        </div>
        <div className="evo-summary-card">
          <p className="evo-summary-card__label">Variantes</p>
          <div className="evo-summary-card__value">{totalVariants.toLocaleString("pt-BR")}</div>
          <div className="evo-summary-card__hint">soma das variantes</div>
        </div>
        <div className="evo-summary-card">
          <p className="evo-summary-card__label">Com baseline</p>
          <div className="evo-summary-card__value">{withBaseline.toLocaleString("pt-BR")}</div>
          <div className="evo-summary-card__hint">baseline configurado</div>
        </div>
        <div className="evo-summary-card">
          <p className="evo-summary-card__label">Última atividade</p>
          <div className="evo-summary-card__value">
            {latestActivity ? relTime(latestActivity) : "—"}
          </div>
          <div className="evo-summary-card__hint">experimento criado</div>
        </div>
      </section>

      {/* Run result */}
      {runDetail?.run && <RunResultCard run={runDetail.run} />}

      {/* Experiments table */}
      {experiments.length === 0 ? (
        <div className="evo-card" style={{ padding: "48px 24px", textAlign: "center" }}>
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
        <div className="evo-table-wrap">
          <table className="evo-table">
            <thead>
              <tr>
                <th>Experimento</th>
                <th>Dataset</th>
                <th>Rubrica</th>
                <th>Variantes</th>
                <th>Baseline</th>
                <th className="evo-table__sortable">Criado</th>
                <th style={{ width: 140 }} />
              </tr>
            </thead>
            <tbody>
              {experiments.map((exp) => (
                <tr key={exp.id}>
                  <td>
                    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                      <span className="evo-table__name">{exp.name}</span>
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
                    <span className="evo-mono evo-muted" style={{ fontSize: 12 }}>
                      {exp.dataset_id.slice(0, 16)}…
                    </span>
                  </td>
                  <td>
                    <span className="evo-mono evo-muted" style={{ fontSize: 12 }}>
                      {exp.rubric_id.slice(0, 16)}…
                    </span>
                  </td>
                  <td>
                    <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                      {exp.variants.map((v) => (
                        <span key={v.name} className="evo-tag">
                          {v.name}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td>
                    <span className="evo-mono evo-muted" style={{ fontSize: 12 }}>
                      {exp.baseline_variant ?? "—"}
                    </span>
                  </td>
                  <td className="evo-muted" style={{ fontSize: 12 }}>
                    {relTime(exp.created_at)}
                  </td>
                  <td>
                    <div className="evo-row" style={{ gap: 4, justifyContent: "flex-end" }}>
                      <form action={runExperimentAction} style={{ display: "inline" }}>
                        <input type="hidden" name="org" value={org} />
                        <input type="hidden" name="project" value={project} />
                        <input type="hidden" name="experiment_id" value={exp.id} />
                        <button type="submit" className="evo-btn evo-btn--sm">
                          <Play size={12} /> Rodar
                        </button>
                      </form>
                      <button
                        type="button"
                        className="evo-btn evo-btn--ghost evo-btn--sm evo-btn--icon"
                        disabled
                        data-status="planned"
                        title="Ações adicionais — em breve"
                        style={{ opacity: 0.4, cursor: "not-allowed" }}
                      >
                        <MoreHorizontal size={14} />
                      </button>
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
                <button type="submit" className="evo-btn evo-btn--primary">
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

      {/* Endpoints reais — referência somente leitura */}
      <section className="evo-card" style={{ marginTop: 12 }}>
        <div className="evo-card__header">
          <div>
            <h3 className="evo-card__title">Endpoints ativos</h3>
            <div className="evo-card__subtitle">Rotas reais do backend que servem este módulo.</div>
          </div>
        </div>
        <div className="evo-card__body">
          <div className="evo-endpoint-list" aria-label="Endpoints do módulo Experiments">
            <div className="evo-endpoint-row">
              <span className="evo-endpoint-row__method evo-endpoint-row__method--get">GET</span>
              <span className="evo-endpoint-row__path" title="/v1/projects/{project_id}/experiments">
                /projects/{"{project_id}"}/experiments
              </span>
              <span className="evo-endpoint-row__note">ativo</span>
            </div>
            <div className="evo-endpoint-row">
              <span className="evo-endpoint-row__method evo-endpoint-row__method--post">POST</span>
              <span className="evo-endpoint-row__path" title="/v1/projects/{project_id}/experiments">
                /projects/{"{project_id}"}/experiments
              </span>
              <span className="evo-endpoint-row__note">ativo · cria experimento</span>
            </div>
            <div className="evo-endpoint-row">
              <span className="evo-endpoint-row__method evo-endpoint-row__method--post">POST</span>
              <span className="evo-endpoint-row__path" title="/v1/experiments/{experiment_id}/run">
                /experiments/{"{experiment_id}"}/run
              </span>
              <span className="evo-endpoint-row__note">ativo · dispara run</span>
            </div>
            <div className="evo-endpoint-row">
              <span className="evo-endpoint-row__method evo-endpoint-row__method--get">GET</span>
              <span className="evo-endpoint-row__path" title="/v1/experiments/{experiment_id}/runs/{run_id}">
                /experiments/{"{experiment_id}"}/runs/{"{run_id}"}
              </span>
              <span className="evo-endpoint-row__note">ativo · detalhe da run</span>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
