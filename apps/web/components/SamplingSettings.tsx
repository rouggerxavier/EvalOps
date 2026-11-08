import Link from "next/link";

import type { Rubric, SamplingConfig, SamplingJob } from "@/lib/types";
import { Card } from "./ui/Card";

const STATUS: Record<string, string> = {
  pending: "Aguardando", queued: "Na fila", queue_error: "Fila indisponível",
  started: "Em execução", uncertain: "Resultado incerto", completed: "Concluída",
  skipped: "Não executada", blocked: "Bloqueada", error: "Erro",
};
const REASON: Record<string, string> = {
  evaluation_queue_unavailable: "A fila será consultada novamente automaticamente.",
  judge_budget_exhausted: "Orçamento do juiz esgotado.", quota_exceeded: "Limite do plano atingido.",
  evaluation_failed: "Falha ao avaliar. Confira a rubrica e a configuração do juiz.",
  already_evaluated: "Já existe uma avaliação com esta rubrica e versão.", not_found: "Trace ou rubrica indisponível.",
};
const RETRYABLE = new Set(["blocked", "error", "queue_error", "uncertain"]);

type Props = {
  org: string;
  project: string;
  data: { config: SamplingConfig; jobs: SamplingJob[]; rubrics: Pick<Rubric, "id" | "slug" | "current_version">[] } | null;
};

export function SamplingSettings({ org, project, data }: Props) {
  return (
    <div id="evaluation-sampling">
      <Card title="Avaliação automática" subtitle="Avalie uma amostra dos novos traces com uma versão fixa de rubrica.">
        {!data ? <p role="alert">Não foi possível carregar a avaliação automática. Atualize a página para tentar novamente.</p> : (
          <>
            <p className="ops-note">Aplica-se a todos os ambientes deste projeto. As avaliações são preparadas a cada minuto. A execução verifica as cotas e o orçamento do juiz. Desativar afeta apenas novos traces.</p>
            <form action="/api/evaluation-sampling" method="post" className="ops-form ops-form__grid" style={{ padding: 0 }}>
              <input type="hidden" name="intent" value="save" />
              <input type="hidden" name="org" value={org} />
              <input type="hidden" name="project" value={project} />
              <label className="quality-gate__checkbox" style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
                <input type="checkbox" name="enabled" defaultChecked={data.config.enabled} style={{ width: "auto" }} /> Ativar avaliação automática
              </label>
              <label className="ops-form__field">
                <span>Traces a avaliar (%)</span>
                <input type="number" name="percentage" min="0" max="100" step="any" required defaultValue={data.config.percentage} />
              </label>
              <label className="ops-form__field">
                <span>Rubrica</span>
                <select name="rubric_id" defaultValue={data.config.rubric_id ?? ""}>
                  <option value="">Nenhuma rubrica</option>
                  {data.rubrics.map((rubric) => <option key={rubric.id} value={rubric.id}>{rubric.slug} (atual v{rubric.current_version})</option>)}
                </select>
              </label>
              <label className="ops-form__field">
                <span>Versão fixa da rubrica</span>
                <input type="number" name="rubric_version" min="1" step="1" defaultValue={data.config.rubric_version ?? ""} />
              </label>
              <p className="ops-note">0% não seleciona traces; 100% seleciona todos. Escolha uma versão existente da rubrica. Alterações só valem para novos traces.</p>
              <button type="submit" className="btn btn--primary">Salvar avaliação automática</button>
            </form>
            <h3>Avaliações automáticas selecionadas</h3>
            <p className="ops-note">Mostrando até 20 registros, com resultados incertos e bloqueados primeiro. Atualize a página para acompanhar o resultado.</p>
            {data.jobs.length === 0 ? <p className="ops-note">Nenhum trace selecionado ainda.</p> : (
              <ol className="ops-stack" style={{ listStyle: "none", padding: 0, margin: 0 }}>
                {data.jobs.map((job) => (
                  <li key={job.trace_id} className="grid-2-eq ops-settings-grid" style={{ borderTop: "1px solid var(--border-subtle)", padding: "16px 0", overflowWrap: "anywhere" }}>
                    <div>
                      <Link href={`/o/${org}/p/${project}/traces/${encodeURIComponent(job.trace_id)}?tab=evaluations`}>{job.trace_id}</Link>
                      <p>{STATUS[job.status] ?? "Estado indisponível"} · {job.execution_attempts} {job.execution_attempts === 1 ? "tentativa" : "tentativas"}</p>
                      <p className="ops-note">Rubrica: {data.rubrics.find((rubric) => rubric.id === job.rubric_id)?.slug ?? "indisponível"} · v{job.rubric_version}</p>
                    </div>
                    <div>
                      {job.reason && REASON[job.reason] ? <p>{REASON[job.reason]}</p> : null}
                      {RETRYABLE.has(job.status) ? (
                        <form action="/api/evaluation-sampling" method="post" className="ops-form" style={{ padding: 0 }}>
                          <input type="hidden" name="intent" value="retry" />
                          <input type="hidden" name="org" value={org} />
                          <input type="hidden" name="project" value={project} />
                          <input type="hidden" name="trace_id" value={job.trace_id} />
                          {job.status === "uncertain" ? (
                            <>
                              <p role="alert">{job.retry_warning ?? "A tentativa anterior pode ter sido cobrada sem resultado salvo. Repetir pode gerar nova cobrança."}</p>
                              <label className="quality-gate__checkbox" style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
                                <input type="checkbox" name="confirm_possible_charge" required style={{ width: "auto" }} /> Entendo que repetir pode gerar nova cobrança.
                              </label>
                            </>
                          ) : null}
                          <button type="submit" className="btn btn--sm btn--ghost">Solicitar nova tentativa</button>
                        </form>
                      ) : null}
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </>
        )}
      </Card>
    </div>
  );
}
