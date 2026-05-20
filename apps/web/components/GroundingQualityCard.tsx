import type { GroundingQuality } from "@/lib/rag";
import { formatScore } from "@/lib/rag";

type Props = { quality: GroundingQuality };

function qualityKind(level: string | undefined): "ok" | "warn" | "err" | "info" {
  if (!level) return "info";
  const v = level.toLowerCase();
  if (v === "high" || v === "good") return "ok";
  if (v === "medium" || v === "fair") return "warn";
  if (v === "low" || v === "poor") return "err";
  return "info";
}

export function GroundingQualityCard({ quality }: Props) {
  const components = quality.quality_components
    ? Object.entries(quality.quality_components)
    : [];
  const reasons = quality.quality_reason_codes ?? [];

  return (
    <div className="evo-card" data-testid="grounding-quality-card">
      <div className="evo-card__header">
        <h3 className="evo-card__title">Grounding & qualidade</h3>
        <div className="evo-row" style={{ gap: 6, flexWrap: "wrap" }}>
          {quality.grounding_ok !== undefined && (
            <span
              className={`evo-badge evo-badge--${quality.grounding_ok ? "ok" : "err"}`}
            >
              <span className="evo-badge__dot" />
              {quality.grounding_ok ? "grounded" : "ungrounded"}
            </span>
          )}
          {quality.quality_level && (
            <span className={`evo-badge evo-badge--${qualityKind(quality.quality_level)}`}>
              <span className="evo-badge__dot" />
              {quality.quality_level}
            </span>
          )}
          {quality.strict_grounding && (
            <span className="evo-badge evo-badge--eval">
              <span className="evo-badge__dot" /> strict
            </span>
          )}
        </div>
      </div>
      <div className="evo-card__body">
        <div
          className="evo-row"
          style={{ gap: 18, fontSize: 12, color: "var(--text-muted)", flexWrap: "wrap" }}
        >
          {quality.quality_score !== undefined && (
            <span>
              <span style={{ color: "var(--text-faint)" }}>score</span>{" "}
              <span className="evo-mono" style={{ color: "var(--text)" }}>
                {formatScore(quality.quality_score)}
              </span>
            </span>
          )}
          {quality.support_rate !== undefined && (
            <span>
              <span style={{ color: "var(--text-faint)" }}>support</span>{" "}
              <span className="evo-mono">{formatScore(quality.support_rate)}</span>
            </span>
          )}
          {quality.citation_count !== undefined && (
            <span>
              <span style={{ color: "var(--text-faint)" }}>citations</span>{" "}
              <span className="evo-mono">{quality.citation_count}</span>
            </span>
          )}
          {quality.unsupported_claim_count !== undefined && (
            <span>
              <span style={{ color: "var(--text-faint)" }}>unsupported</span>{" "}
              <span
                className="evo-mono"
                style={{
                  color: quality.unsupported_claim_count > 0 ? "var(--warn)" : "var(--text)",
                }}
              >
                {quality.unsupported_claim_count}
              </span>
            </span>
          )}
          {quality.retry_count !== undefined && (
            <span>
              <span style={{ color: "var(--text-faint)" }}>retries</span>{" "}
              <span className="evo-mono">{quality.retry_count}</span>
            </span>
          )}
          {quality.repair_count !== undefined && (
            <span>
              <span style={{ color: "var(--text-faint)" }}>repairs</span>{" "}
              <span className="evo-mono">{quality.repair_count}</span>
            </span>
          )}
        </div>

        {reasons.length > 0 && (
          <div style={{ marginTop: 14 }}>
            <div
              style={{
                fontSize: 11,
                color: "var(--text-faint)",
                textTransform: "uppercase",
                letterSpacing: "0.04em",
                marginBottom: 6,
              }}
            >
              Reason codes
            </div>
            <div className="evo-row" style={{ flexWrap: "wrap", gap: 6 }}>
              {reasons.map((code) => (
                <span key={code} className="evo-tag">
                  {code}
                </span>
              ))}
            </div>
          </div>
        )}

        {components.length > 0 && (
          <div style={{ marginTop: 14 }}>
            <div
              style={{
                fontSize: 11,
                color: "var(--text-faint)",
                textTransform: "uppercase",
                letterSpacing: "0.04em",
                marginBottom: 6,
              }}
            >
              Components
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr auto", rowGap: 4, columnGap: 12 }}>
              {components.map(([k, v]) => (
                <span
                  key={k}
                  style={{ display: "contents" }}
                >
                  <span style={{ fontSize: 12, color: "var(--text-muted)" }}>{k}</span>
                  <span className="evo-mono" style={{ fontSize: 12 }}>
                    {formatScore(v, 2)}
                  </span>
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
