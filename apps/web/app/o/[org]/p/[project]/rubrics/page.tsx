import Link from "next/link";
import { Clock, Plus } from "lucide-react";

import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { createRubricAction, createRubricVersionAction } from "@/lib/actions";
import { getRubrics, getRubricVersions, hasAuthToken, resolveProject } from "@/lib/api";
import { getActiveEnvironment } from "@/lib/active-env";
import { ignoredFieldsNotice, safeErrorMessage } from "@/lib/safe-error";
import type { Rubric, RubricVersion } from "@/lib/types";

import { getRubricReport } from "../rubric-report";

type Props = {
  params: Promise<{ org: string; project: string }>;
  searchParams: Promise<{
    ignored?: string;
    rubric?: string;
    error?: string;
    created?: string;
    versioned?: string;
    environment?: string;
  }>;
};

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
  const report = selected ? reportsByRubric.get(selected.id) ?? null : null;
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
            <label className="ops-form__field">
              <span>YAML da rubrica</span>
              <textarea name="yaml_source" required rows={12} defaultValue={DEFAULT_YAML} />
            </label>
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
                    <label className="ops-form__field">
                      <span>YAML</span>
                      <textarea
                        name="yaml_source"
                        required
                        rows={12}
                        defaultValue={latestVersion?.yaml_source ?? ""}
                      />
                    </label>
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
                  <span>Aprovação, 7 dias</span>
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
