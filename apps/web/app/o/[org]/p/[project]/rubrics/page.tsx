import Link from "next/link";
import { Clock, Plus } from "lucide-react";

import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { RubricYamlEditor } from "@/components/RubricYamlEditor";
import { AreaChart, Card, EmptyState, Metric } from "@/components/ui/index";
import { createRubricAction, createRubricVersionAction, triggerEvaluationBatchAction } from "@/lib/actions";
import { getCliJudges, getRubricReport, getRubrics, getRubricVersions, hasAuthToken, resolveProject } from "@/lib/api";
import { getActiveEnvironment } from "@/lib/active-env";
import { formatCost, formatPercent } from "@/lib/format";
import { ignoredFieldsNotice, safeErrorMessage } from "@/lib/safe-error";
import type { Rubric, RubricReport, RubricReportWindow, RubricVersion } from "@/lib/types";

type Props = {
  params: Promise<{ org: string; project: string }>;
  searchParams: Promise<{
    ignored?: string;
    rubric?: string;
    error?: string;
    created?: string;
    versioned?: string;
    batched?: string;
    window?: string;
    environment?: string;
  }>;
};

const REPORT_WINDOWS: RubricReportWindow[] = ["24h", "7d", "30d", "90d"];
const WINDOW_LABELS: Record<RubricReportWindow, string> = {
  "24h": "Últimas 24h",
  "7d": "Últimos 7 dias",
  "30d": "Últimos 30 dias",
  "90d": "Últimos 90 dias",
};

const pctOrDash = (value: number | null) => (value == null ? "Sem dados" : formatPercent(value));
const scoreOrDash = (value: number | null) => (value == null ? "Sem dados" : value.toFixed(2));

const DEFAULT_YAML = `slug: answer-quality
name: Answer Quality
description: Check if the answer is acceptable
threshold: 0.7
aggregate: weighted_mean
evaluators:
  - id: length_check
    type: length_bounds
    weight: 1.0
    config:
      target: trace.output.assistant_message
      unit: chars
      min: 20
      max: 800`;

function relTime(iso: string): string {
  const diff = Date.now() - Date.parse(iso);
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "agora";
  if (mins < 60) return `há ${mins} min`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `há ${hrs} h`;
  return `há ${Math.floor(hrs / 24)} dias`;
}

function fmtPct(value: number | null): string {
  return value === null ? "Sem dados" : `${Math.round(value * 100)}%`;
}

function latestVersionFor(rubric: Rubric, versions: RubricVersion[]): RubricVersion | null {
  return versions.find((version) => version.version === rubric.current_version) ?? versions[versions.length - 1] ?? null;
}

export default async function RubricsPage({ params, searchParams }: Props) {
  const { org, project } = await params;
  const qp = await searchParams;

  if (!(await hasAuthToken())) return <AuthRequiredPanel layout="main" />;

  const resolved = await resolveProject(org, project);
  const environment = await getActiveEnvironment(qp.environment);
  const { data: rubrics } = await getRubrics(resolved.project_id);
  const cliJudges = await getCliJudges();
  const selectedId = qp.rubric ?? rubrics[0]?.id ?? null;
  const selected = rubrics.find((rubric) => rubric.id === selectedId) ?? rubrics[0] ?? null;

  const reports = await Promise.all(
    rubrics.map((rubric) =>
      getRubricReport(resolved.project_id, rubric.id, "7d", environment).catch(() => null),
    ),
  );
  const reportsByRubric = new Map(rubrics.map((rubric, index) => [rubric.id, reports[index]]));

  const versions: RubricVersion[] = selected ? (await getRubricVersions(selected.id)).data : [];
  const latestVersion = selected ? latestVersionFor(selected, versions) : null;
  const evaluators = latestVersion?.parsed_spec?.evaluators ?? [];
  const reportWindow = REPORT_WINDOWS.find((w) => w === qp.window) ?? "7d";
  // The list keeps 7d; the selected rubric follows the chosen window. A failed report must not hide the definition.
  const report: RubricReport | null = selected
    ? reportWindow === "7d"
      ? reportsByRubric.get(selected.id) ?? null
      : await getRubricReport(resolved.project_id, selected.id, reportWindow, environment).catch(() => null)
    : null;
  // Trend of the newest version that has runs; the version table compares all of them.
  const trendVersion = report?.by_version.at(-1)?.rubric_version ?? null;
  const trendSeries = (report?.by_day ?? [])
    .filter((d) => d.rubric_version === trendVersion && d.avg_score != null)
    .map((d) => ({ label: `${d.day.slice(8, 10)}/${d.day.slice(5, 7)}`, value: d.avg_score as number }));
  const baseUrl = `/o/${org}/p/${project}/rubrics`;
  const errorMessage = qp.error ? safeErrorMessage(qp.error, "Falha ao salvar rubrica.") : null;
  const successMessage = qp.created ? "Rubrica criada." : qp.versioned ? "Nova versão salva." : null;
  const ignoredNotice = ignoredFieldsNotice(qp.ignored);

  return (
    <div className="page ops-page">
      <header className="ops-page-header">
        <div className="ops-page-header__copy">
          <h1 className="ops-page-header__title">Rubricas</h1>
          <p className="ops-page-header__subtitle">
            O que a IA deveria fazer. Cada execução é avaliada com base nisso.
          </p>
        </div>
        <details className="ops-create" open={rubrics.length === 0}>
          <summary className="btn btn--sm btn--primary"><Plus size={12} /> Nova rubrica</summary>
          <form action={createRubricAction} className="ops-form">
            <input type="hidden" name="org" value={org} />
            <input type="hidden" name="project" value={project} />
            <input type="hidden" name="project_id" value={resolved.project_id} />
            <RubricYamlEditor label="YAML da rubrica" defaultValue={DEFAULT_YAML} judges={cliJudges} />
            <button type="submit" className="btn btn--sm btn--primary">Criar rubrica</button>
          </form>
        </details>
      </header>

      {errorMessage && <div className="ops-flash ops-flash--error" role="alert">{errorMessage}</div>}
      {successMessage && (
        <div className="ops-flash ops-flash--success" role="status">
          {successMessage}{ignoredNotice ? ` ${ignoredNotice}` : ""}
        </div>
      )}
      {qp.batched && (
        <div className="ops-flash ops-flash--success" role="status">
          {qp.batched === "0"
            ? "Nenhum trace novo para avaliar: os traces que batem com o filtro já têm resultado nesta versão."
            : `${qp.batched} traces na fila. Os resultados aparecem no relatório abaixo conforme forem avaliados; recarregue a página em alguns instantes.`}
        </div>
      )}

      {selected ? (
        <div className="ops-rubrics-layout">
          <nav className="ops-rubrics-list ops-panel" aria-label="Lista de rubricas">
            <header className="ops-panel__header"><h2>{rubrics.length} rubricas</h2></header>
            {rubrics.map((rubric) => {
              const active = rubric.id === selected.id;
              const itemReport = reportsByRubric.get(rubric.id);
              return (
                <Link
                  key={rubric.id}
                  href={`${baseUrl}?rubric=${encodeURIComponent(rubric.id)}`}
                  className={`ops-rubrics-list__item${active ? " is-active" : ""}`}
                  aria-current={active ? "page" : undefined}
                >
                  <span className="ops-rubrics-list__top">
                    <strong>{rubric.slug}</strong>
                    <span className="ops-status ops-status--unknown"><Clock size={13} aria-hidden="true" /> Sem meta</span>
                  </span>
                  <span className="ops-rubrics-list__meta">
                    v{rubric.current_version} · aprovação {fmtPct(itemReport?.totals.pass_rate ?? null)}
                  </span>
                </Link>
              );
            })}
          </nav>

          <div className="ops-rubric-detail">
            <section className="ops-panel">
              <header className="ops-rubric-detail__header">
                <div>
                  <h2>{selected.slug}</h2>
                  <p>{selected.description ?? "Sem descrição disponível."}</p>
                </div>
                <details className="ops-create ops-create--version">
                  <summary className="btn btn--sm">Salvar nova versão</summary>
                  <form action={createRubricVersionAction} className="ops-form">
                    <input type="hidden" name="org" value={org} />
                    <input type="hidden" name="project" value={project} />
                    <input type="hidden" name="rubric_id" value={selected.id} />
                    <RubricYamlEditor label="YAML" defaultValue={latestVersion?.yaml_source ?? ""} judges={cliJudges} />
                    <button type="submit" className="btn btn--sm btn--primary">Criar versão</button>
                  </form>
                </details>
              </header>
              <div className="ops-rubric-metrics">
                <div className="ops-rubric-metric">
                  <span>Corte de aprovação</span>
                  <strong>{selected.threshold.toFixed(2)}</strong>
                </div>
                <div className="ops-rubric-metric">
                  <span>Aprovação, {WINDOW_LABELS[reportWindow].toLowerCase()}</span>
                  <strong>{fmtPct(report?.totals.pass_rate ?? null)}</strong>
                </div>
                <div className="ops-rubric-metric">
                  <span>Execuções avaliadas</span>
                  <strong>{report?.totals.runs.toLocaleString("pt-BR") ?? "Sem dados"}</strong>
                </div>
              </div>
            </section>

            <section className="ops-panel">
              <header className="ops-panel__header">
                <h3>Definição</h3>
                <span className="ops-mono">YAML</span>
              </header>
              <pre className="ops-code">{latestVersion?.yaml_source ?? "Sem dados de YAML para esta versão."}</pre>
            </section>

            <div className="ops-rubric-bottom">
              <section className="ops-panel">
                <header className="ops-panel__header"><h3>Avaliadores</h3></header>
                {evaluators.length ? (
                  evaluators.map((evaluator) => {
                    const model = evaluator.config?.model;
                    return (
                      <div className="ops-rubric-row" key={evaluator.id}>
                        <div>
                          <span className="ops-mono">{evaluator.id}</span>
                          <span className="ops-rubric-row__secondary">{evaluator.type}</span>
                        </div>
                        {typeof model === "string" && <span className="ops-mono">{model}</span>}
                      </div>
                    );
                  })
                ) : (
                  <p className="ops-panel__empty">Sem dados de avaliadores.</p>
                )}
              </section>

              <section className="ops-panel">
                <header className="ops-panel__header"><h3>Versões</h3></header>
                {versions.length ? (
                  [...versions].reverse().map((version) => (
                    <div className="ops-rubric-row" key={version.id}>
                      <strong>v{version.version}{version.version === selected.current_version ? " (atual)" : ""}</strong>
                      <span className="ops-panel__muted">{relTime(version.created_at)}</span>
                    </div>
                  ))
                ) : (
                  <p className="ops-panel__empty">Sem dados de versões.</p>
                )}
              </section>
            </div>

            <section className="ops-rubric-results" aria-label="Resultados da rubrica">
              <header className="ops-rubric-results__header">
                <h3>Resultados</h3>
                <form method="get" action={baseUrl} className="ops-rubric-results__filters">
                  <input type="hidden" name="rubric" value={selected.id} />
                  <select className="filter-select" name="window" defaultValue={reportWindow} aria-label="Período">
                    {REPORT_WINDOWS.map((w) => (
                      <option key={w} value={w}>{WINDOW_LABELS[w]}</option>
                    ))}
                  </select>
                  <select className="filter-select" name="environment" defaultValue={environment ?? ""} aria-label="Ambiente">
                    <option value="">Qualquer ambiente</option>
                    <option value="prod">Produção</option>
                    <option value="staging">Staging</option>
                    <option value="dev">Dev</option>
                  </select>
                  <button type="submit" className="btn btn--sm">Aplicar</button>
                </form>
              </header>

              {!report ? (
                <EmptyState
                  title="Não foi possível carregar o relatório"
                  description="Tente recarregar a página. A definição da rubrica acima continua disponível."
                />
              ) : report.totals.runs === 0 ? (
                <EmptyState
                  title="Nenhuma avaliação neste período"
                  description={`${report.trace_count.toLocaleString("pt-BR")} traces no período ainda não foram avaliados com esta rubrica. Use "Avaliar em lote" abaixo para começar.`}
                />
              ) : (
                <>
                  <section className="kpi-grid kpi-grid--5">
                    <Metric label="Avaliações" value={report.totals.runs.toLocaleString("pt-BR")} delta={`${report.trace_count.toLocaleString("pt-BR")} traces no período`} />
                    <Metric
                      label="Aprovação"
                      value={pctOrDash(report.totals.pass_rate)}
                      delta={`${report.totals.passed} aprovadas · ${report.totals.failed} reprovadas`}
                    />
                    <Metric label="Score médio" value={scoreOrDash(report.totals.avg_score)} />
                    <Metric
                      label="Sem resultado"
                      value={(report.totals.unknown + report.totals.errors).toLocaleString("pt-BR")}
                      delta={`${report.totals.unknown} pendentes ou parciais · ${report.totals.errors} com erro`}
                      deltaTone={report.totals.unknown + report.totals.errors > 0 ? "down" : "neutral"}
                    />
                    <Metric label="Custo" value={formatCost(report.totals.cost_usd)} />
                  </section>

                  <div className="ops-rubric-bottom">
                    <Card title="Tendência do score" subtitle={`Score médio por dia · v${trendVersion}`}>
                      <AreaChart data={trendSeries} color="var(--ops-approved)" />
                    </Card>

                    <Card title="Comparação entre versões" subtitle="Aprovação conta só avaliações com resultado" flush>
                      <table className="t">
                        <thead>
                          <tr>
                            <th>Versão</th>
                            <th className="t__num">Avaliações</th>
                            <th className="t__num">Aprovação</th>
                            <th className="t__num">Score médio</th>
                            <th className="t__num">Sem resultado</th>
                            <th className="t__num">Custo</th>
                          </tr>
                        </thead>
                        <tbody>
                          {report.by_version.map((v) => (
                            <tr key={v.rubric_version}>
                              <td className="ops-mono">v{v.rubric_version}</td>
                              <td className="t__num">{v.runs}</td>
                              <td className="t__num">{pctOrDash(v.pass_rate)}</td>
                              <td className="t__num">{scoreOrDash(v.avg_score)}</td>
                              <td className="t__num">{v.unknown + v.errors}</td>
                              <td className="t__num">{formatCost(v.cost_usd)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </Card>
                  </div>

                  <Card title="Por avaliador" subtitle="Cada critério da rubrica, por versão" flush>
                    <table className="t">
                      <thead>
                        <tr>
                          <th>Versão</th>
                          <th>Avaliador</th>
                          <th className="t__num">Avaliações</th>
                          <th className="t__num">Aprovação</th>
                          <th className="t__num">Score médio</th>
                          <th className="t__num">Com erro</th>
                        </tr>
                      </thead>
                      <tbody>
                        {report.by_evaluator.map((e) => (
                          <tr key={`${e.rubric_version}-${e.evaluator}`}>
                            <td className="ops-mono">v{e.rubric_version}</td>
                            <td>{e.evaluator}</td>
                            <td className="t__num">{e.runs}</td>
                            <td className="t__num">{pctOrDash(e.pass_rate)}</td>
                            <td className="t__num">{scoreOrDash(e.avg_score)}</td>
                            <td className="t__num">{e.errors}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </Card>
                </>
              )}

              <Card title="Avaliar em lote" subtitle="Avaliações concluídas com veredito nesta rubrica e versão são ignoradas. Avaliações com erro ou parciais sem veredito podem voltar à fila e gerar novo custo.">
                <form action={triggerEvaluationBatchAction} className="ops-batch-form">
                  <input type="hidden" name="org" value={org} />
                  <input type="hidden" name="project" value={project} />
                  <input type="hidden" name="project_id" value={resolved.project_id} />
                  <input type="hidden" name="rubric_id" value={selected.id} />
                  <label className="ops-form__field">
                    <span>Versão da rubrica</span>
                    <select name="rubric_version" defaultValue={String(selected.current_version)}>
                      {[...versions].reverse().map((v) => (
                        <option key={v.id} value={v.version}>v{v.version}</option>
                      ))}
                    </select>
                  </label>
                  <label className="ops-form__field">
                    <span>Ambiente</span>
                    <select name="environment" defaultValue={environment ?? ""}>
                      <option value="">Qualquer ambiente</option>
                      <option value="prod">Produção</option>
                      <option value="staging">Staging</option>
                      <option value="dev">Dev</option>
                    </select>
                  </label>
                  <label className="ops-form__field">
                    <span>Máximo de traces</span>
                    <input type="number" name="limit" min={1} max={500} defaultValue={100} required />
                  </label>
                  <label className="ops-form__field">
                    <span>Nome do trace contém (opcional)</span>
                    <input name="name_contains" maxLength={255} placeholder="ex: refund" />
                  </label>
                  <button type="submit" className="btn btn--sm btn--primary">Enfileirar avaliações</button>
                </form>
              </Card>
            </section>
          </div>
        </div>
      ) : (
        <section className="ops-panel ops-empty">
          <h2 className="ops-empty__title">Nenhuma rubrica</h2>
          <p className="ops-empty__description">Crie uma rubrica para avaliar execuções do projeto.</p>
        </section>
      )}
    </div>
  );
}
