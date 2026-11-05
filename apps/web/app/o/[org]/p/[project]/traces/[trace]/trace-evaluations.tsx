import { CheckCircle2, CircleX, HelpCircle } from "lucide-react";

import { Card } from "@/components/ui/Card";
import { ScoreCell } from "@/components/ui/ScoreCell";
import { formatCost, formatRelativeTime } from "@/lib/format";
import { evaluationErrorText } from "@/lib/trace-display";
import type { EvaluationRun, Rubric } from "@/lib/types";

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
  const scoreRows = orderedRuns.flatMap((run) => run.scores.map((score) => ({ run, score })));
  const noScores = scoreRows.length === 0;

  return (
    <Card
      title="Avaliações"
      subtitle={`${runs.length} execução${runs.length === 1 ? "" : "ões"} · mais recente ${formatRelativeTime(orderedRuns[0].created_at)}`}
      flush
      className="ops-detail__evaluations"
    >
      {noScores ? (
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
              {scoreRows.map(({ run, score }) => {
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
                    <td>{reasoning || <span className="t__faint">Sem dados</span>}</td>
                    <td className="t__num">{error ? <span className="t__faint">Sem dados</span> : <ScoreCell value={score.score} />}</td>
                    <td className="t__num">{formatCost(score.cost_usd)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
