import type { RagSummary } from "@/lib/rag";
import { formatScore } from "@/lib/rag";

type Props = { summary: RagSummary };

function qualityBadgeKind(level: string | undefined): "ok" | "warn" | "err" | "info" {
  if (!level) return "info";
  const v = level.toLowerCase();
  if (v === "high" || v === "good") return "ok";
  if (v === "medium" || v === "fair") return "warn";
  if (v === "low" || v === "poor") return "err";
  return "info";
}

export function RAGSummaryHeader({ summary }: Props) {
  const chips: Array<{ key: string; label: string; value: string; kind?: "ok" | "warn" | "err" | "info" | "eval" }> = [];

  if (summary.model) chips.push({ key: "model", label: "model", value: summary.model });
  if (summary.pipeline_version) chips.push({ key: "pipeline", label: "pipeline", value: summary.pipeline_version });

  if (summary.retrieved_count !== undefined) {
    chips.push({ key: "retrieved", label: "retrieved", value: String(summary.retrieved_count) });
  }
  if (summary.citation_count !== undefined) {
    chips.push({ key: "citations", label: "citations", value: String(summary.citation_count) });
  }
  if (summary.grounding_ok !== undefined) {
    chips.push({
      key: "grounding",
      label: "grounding",
      value: summary.grounding_ok ? "ok" : "fail",
      kind: summary.grounding_ok ? "ok" : "err",
    });
  }
  if (summary.quality_level) {
    chips.push({
      key: "quality",
      label: "quality",
      value: summary.quality_level,
      kind: qualityBadgeKind(summary.quality_level),
    });
  }
  if (summary.quality_score !== undefined) {
    chips.push({ key: "qscore", label: "score", value: formatScore(summary.quality_score) });
  }
  if (summary.strict_grounding) {
    chips.push({ key: "strict", label: "strict", value: "on", kind: "eval" });
  }

  const showUsageWarn = !summary.has_usage_signal;

  if (chips.length === 0 && !showUsageWarn) return null;

  return (
    <div
      className="evo-card"
      style={{ marginBottom: "var(--sp-3)" }}
      data-testid="rag-summary-header"
    >
      <div className="evo-card__header">
        <h3 className="evo-card__title">Resumo RAG</h3>
        <span className="evo-card__subtitle">Sinais extraídos do trace</span>
      </div>
      <div className="evo-card__body">
        <div className="evo-row" style={{ flexWrap: "wrap", gap: 8 }}>
          {chips.map((c) =>
            c.kind ? (
              <span key={c.key} className={`evo-badge evo-badge--${c.kind}`}>
                <span className="evo-badge__dot" />
                {c.label}: {c.value}
              </span>
            ) : (
              <span key={c.key} className="evo-tag" style={{ height: 22, padding: "2px 8px" }}>
                <span style={{ color: "var(--text-faint)", marginRight: 4 }}>{c.label}</span>
                <span style={{ color: "var(--text-dim)" }}>{c.value}</span>
              </span>
            )
          )}
        </div>
        {showUsageWarn && (
          <p
            style={{
              margin: "12px 0 0",
              fontSize: 12,
              color: "var(--text-muted)",
            }}
          >
            Tokens/custo zerados — emissor não enviou <code className="evo-mono">tokens_in</code>,{" "}
            <code className="evo-mono">tokens_out</code> ou <code className="evo-mono">cost_usd</code>{" "}
            por span.
          </p>
        )}
      </div>
    </div>
  );
}
