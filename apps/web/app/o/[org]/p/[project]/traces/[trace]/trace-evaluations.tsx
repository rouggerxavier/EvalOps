import { CheckCircle2, CircleX, HelpCircle } from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { ScoreCell } from "@/components/ui/ScoreCell";
import { formatCost, formatRelativeTime } from "@/lib/format";
import { evaluationErrorText, runVerdict } from "@/lib/trace-display";
import type { EvaluationRun, Rubric } from "@/lib/types";

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function scoreStatus(passed: boolean, error: string | null) {
  if (error) return { label: "Sem dados", className: "ops-status--unknown", Icon: HelpCircle };
  return passed
    ? { label: "Aprovado", className: "ops-status--approved", Icon: CheckCircle2 }
    : { label: "Reprovado", className: "ops-status--rejected", Icon: CircleX };
}

export function TraceEvaluations({ runs, rubrics }: { runs: EvaluationRun[]; rubrics: Pick<Rubric, "id" | "slug">[] }) {
  if (runs.length === 0) {
    return (
      <Card title="Avaliações" subtitle="Sem avaliações registradas" className="ops-detail__evaluations">
        <p className="muted" style={{ margin: 0 }}>Use o botão Avaliar, acima, para medir este trace com uma rubrica.</p>
      </Card>
    );
  }

  const slugById = new Map(rubrics.map((rubric) => [rubric.id, rubric.slug]));
  const orderedRuns = [...runs].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));

  return (
    <div className="col ops-detail__evaluations">
      {orderedRuns.map((run) => {
        const verdict = runVerdict(run);
        const meta = run.run_metadata ?? {};
        const raised = strings(meta.raised_flags);
        return (
          <Card
            key={run.id}
            title={`${slugById.get(run.rubric_id) ?? run.rubric_id.slice(0, 12)} v${run.rubric_version}`}
            subtitle={`${formatRelativeTime(run.created_at)} · ${run.cost_usd === null ? "custo desconhecido" : formatCost(run.cost_usd)} · ${run.triggered_by}`}
            action={
              <span className="row" style={{ gap: 10 }}>
                {run.aggregate_score === null ? null : <ScoreCell value={run.aggregate_score} />}
                <Badge variant={verdict.variant}>{verdict.label}</Badge>
              </span>
            }
            flush
          >
            <div style={{ padding: "0 16px", overflowWrap: "anywhere" }}>
              {strings(run.error?.reasons).map((reason) => (
                <p key={reason} style={{ color: "var(--warning)" }}>{evaluationErrorText(reason)}</p>
              ))}
              {run.passed === null && meta.partial_failure ? (
                <p style={{ color: "var(--warning)" }}>
                  Parte dos avaliadores não mediu, então não há veredito. A nota cobre só o restante. Avalie de novo depois de resolver a causa.
                </p>
              ) : null}
              {raised.length > 0 ? <p style={{ color: "var(--danger)" }}>Flag crítica levantada: {raised.join(", ")}.</p> : null}
            </div>
            {run.scores.length === 0 ? (
              <p className="t__empty">Sem dados de avaliadores para estas execuções.</p>
            ) : (
              <div className="table-wrap">
                <table className="t">
                  <thead>
                    <tr>
                      <th>Situação</th>
                      <th>Rubrica</th>
                      <th>O que o juiz disse</th>
                      <th className="t__num">Score</th>
                      <th className="t__num">Custo</th>
                    </tr>
                  </thead>
                  <tbody>
                    {run.scores.map((score) => {
                      const raw = score.raw_output ?? {};
                      const error = typeof raw.error === "string" ? raw.error : null;
                      const status = scoreStatus(score.passed, error);
                      const reasoning = error ? evaluationErrorText(error) : score.reasoning;
                      return (
                        <tr key={score.id}>
                          <td>
                            <span className={`ops-status ${status.className}`}>
                              <status.Icon size={13} aria-hidden="true" />
                              {status.label}
                            </span>
                          </td>
                          <td>
                            <span className="t__name">{slugById.get(run.rubric_id) ?? run.rubric_id.slice(0, 12)}</span>
                            <span className="t__faint">v{run.rubric_version} · {score.evaluator_slug}</span>
                          </td>
                          <td>
                            {reasoning || <span className="t__faint">Sem dados</span>}
                            {strings(raw.flags).map((flag) => <span key={flag} className="tag">{flag}</span>)}
                            {Array.isArray(raw.samples) && raw.samples.length > 1 && typeof raw.stddev === "number" ? (
                              <span className="t__faint">{raw.samples.length} amostras · desvio {raw.stddev.toFixed(2)}</span>
                            ) : null}
                          </td>
                          <td className="t__num">{error ? <span className="t__faint">Sem dados</span> : <ScoreCell value={score.score} />}</td>
                          <td className="t__num">{score.cost_usd === null ? <span className="t__faint">Sem dados</span> : formatCost(score.cost_usd)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        );
      })}
    </div>
  );
}
