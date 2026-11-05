import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { ScoreCell } from "@/components/ui/ScoreCell";
import { formatCost, formatRelativeTime } from "@/lib/format";
import { evaluationErrorText, runVerdict } from "@/lib/trace-display";
import type { EvaluationRun, EvaluationScore, Rubric } from "@/lib/types";

const ROW_STYLE = {
  padding: "12px 16px",
  borderBottom: "1px solid var(--border-subtle)",
  display: "flex",
  flexDirection: "column",
  gap: 6,
} as const;

const TEXT_STYLE = { margin: 0, maxWidth: "72ch", fontSize: 13, lineHeight: 1.5, color: "var(--fg-2)", overflowWrap: "anywhere" } as const;

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function ScoreRow({ score }: { score: EvaluationScore }) {
  const raw = score.raw_output ?? {};
  const error = typeof raw.error === "string" ? raw.error : null;
  const flags = strings(raw.flags);
  const samples = Array.isArray(raw.samples) ? raw.samples.length : 0;
  return (
    <div style={ROW_STYLE}>
      <div className="row" style={{ justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
        <span className="mono" style={{ fontSize: 13, color: "var(--fg-1)" }}>{score.evaluator_slug}</span>
        {error ? (
          <Badge>não mediu</Badge>
        ) : (
          <span className="row" style={{ gap: 10 }}>
            <ScoreCell value={score.score} />
            <Badge variant={score.passed ? "ok" : "err"}>{score.passed ? "passou" : "falhou"}</Badge>
          </span>
        )}
      </div>
      {error ? <p style={{ ...TEXT_STYLE, color: "var(--warning)" }}>{evaluationErrorText(error)}</p> : null}
      {!error && score.reasoning ? <p style={TEXT_STYLE}>{score.reasoning}</p> : null}
      {flags.length > 0 ? (
        <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
          {flags.map((flag) => (
            <span key={flag} className="tag">{flag}</span>
          ))}
        </div>
      ) : null}
      {samples > 1 && typeof raw.stddev === "number" ? (
        <span className="mono" style={{ fontSize: 11, color: "var(--fg-3)" }}>
          {samples} amostras · desvio {raw.stddev.toFixed(2)}
        </span>
      ) : null}
    </div>
  );
}

function RunCard({ run, rubricSlug }: { run: EvaluationRun; rubricSlug: string }) {
  const verdict = runVerdict(run);
  const meta = run.run_metadata ?? {};
  const raised = strings(meta.raised_flags);
  const reasons = strings(run.error?.reasons);
  return (
    <Card
      title={`${rubricSlug} v${run.rubric_version}`}
      subtitle={`${formatRelativeTime(run.created_at)} · ${formatCost(run.cost_usd)} · ${run.triggered_by}`}
      action={
        <span className="row" style={{ gap: 10 }}>
          {run.aggregate_score === null ? null : <ScoreCell value={run.aggregate_score} />}
          <Badge variant={verdict.variant}>{verdict.label}</Badge>
        </span>
      }
      flush
    >
      {reasons.map((reason) => (
        <p key={reason} style={{ ...TEXT_STYLE, padding: "12px 16px", color: "var(--warning)" }}>
          {evaluationErrorText(reason)}
        </p>
      ))}
      {run.passed === null && meta.partial_failure ? (
        <p style={{ ...TEXT_STYLE, padding: "12px 16px", color: "var(--warning)" }}>
          Parte dos avaliadores não mediu, então não há veredito. A nota cobre só o restante. Avalie de novo depois de resolver a causa.
        </p>
      ) : null}
      {raised.length > 0 ? (
        <p style={{ ...TEXT_STYLE, padding: "12px 16px", color: "var(--danger)" }}>
          Flag crítica levantada: {raised.join(", ")}.
        </p>
      ) : null}
      {run.scores.map((score) => (
        <ScoreRow key={score.id} score={score} />
      ))}
    </Card>
  );
}

export function TraceEvaluations({ runs, rubrics }: { runs: EvaluationRun[]; rubrics: Pick<Rubric, "id" | "slug">[] }) {
  if (runs.length === 0) {
    return (
      <Card title="Avaliações" subtitle="Nenhuma ainda">
        <p className="muted" style={{ margin: 0 }}>Use o botão Avaliar, acima, para medir este trace com uma rubrica.</p>
      </Card>
    );
  }
  const slugById = new Map(rubrics.map((rubric) => [rubric.id, rubric.slug]));
  return (
    <div className="col">
      {runs.map((run) => (
        <RunCard key={run.id} run={run} rubricSlug={slugById.get(run.rubric_id) ?? run.rubric_id.slice(0, 12)} />
      ))}
    </div>
  );
}
