import type { AnswerPreview } from "@/lib/rag";
import { formatScore } from "@/lib/rag";

type Props = { answer: AnswerPreview };

export function AnswerPreviewCard({ answer }: Props) {
  const noAnswer = answer.has_answer === false || !answer.answer_preview;

  return (
    <div className="evo-card" data-testid="answer-preview-card">
      <div className="evo-card__header">
        <h3 className="evo-card__title">Resposta</h3>
        <div className="evo-row" style={{ gap: 6 }}>
          {answer.has_answer === true && (
            <span className="evo-badge evo-badge--ok">
              <span className="evo-badge__dot" /> has answer
            </span>
          )}
          {answer.has_answer === false && (
            <span className="evo-badge evo-badge--warn">
              <span className="evo-badge__dot" /> no answer
            </span>
          )}
          {answer.truncated && (
            <span className="evo-badge evo-badge--info">
              <span className="evo-badge__dot" /> truncado
            </span>
          )}
        </div>
      </div>
      <div className="evo-card__body">
        {answer.answer_preview ? (
          <p
            style={{
              margin: 0,
              fontSize: 13,
              lineHeight: 1.55,
              color: "var(--text)",
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
            }}
          >
            {answer.answer_preview}
          </p>
        ) : (
          <p style={{ margin: 0, fontSize: 12, color: "var(--text-muted)" }}>
            {noAnswer
              ? "Sem resposta gerada neste trace."
              : "Resposta não capturada como preview."}
          </p>
        )}

        <div
          className="evo-row"
          style={{
            gap: 14,
            marginTop: 14,
            fontSize: 12,
            color: "var(--text-muted)",
            flexWrap: "wrap",
          }}
        >
          {answer.source_count !== undefined && (
            <span>
              <span style={{ color: "var(--text-faint)" }}>sources</span>{" "}
              <span className="evo-mono">{answer.source_count}</span>
            </span>
          )}
          {answer.citation_count !== undefined && (
            <span>
              <span style={{ color: "var(--text-faint)" }}>citations</span>{" "}
              <span className="evo-mono">{answer.citation_count}</span>
            </span>
          )}
          {answer.quality_level && (
            <span>
              <span style={{ color: "var(--text-faint)" }}>quality</span>{" "}
              <span className="evo-mono">{answer.quality_level}</span>
            </span>
          )}
          {answer.quality_score !== undefined && (
            <span>
              <span style={{ color: "var(--text-faint)" }}>score</span>{" "}
              <span className="evo-mono">{formatScore(answer.quality_score)}</span>
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
