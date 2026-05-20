import type { RetrievalSummary } from "@/lib/rag";
import { formatScore, shortRef } from "@/lib/rag";

type Props = { retrieval: RetrievalSummary };

const MAX_ROWS = 8;

export function RetrievalSummaryCard({ retrieval }: Props) {
  const chunkCount = retrieval.chunk_refs?.length ?? 0;
  const docCount = retrieval.doc_refs?.length ?? 0;

  return (
    <div className="evo-card" data-testid="retrieval-summary-card">
      <div className="evo-card__header">
        <h3 className="evo-card__title">Retrieval</h3>
        <div className="evo-row" style={{ gap: 6 }}>
          {retrieval.retrieval_mode && (
            <span className="evo-tag">{retrieval.retrieval_mode}</span>
          )}
          {retrieval.truncated && (
            <span className="evo-badge evo-badge--warn">
              <span className="evo-badge__dot" /> truncado
            </span>
          )}
        </div>
      </div>
      <div className="evo-card__body">
        <div
          className="evo-row"
          style={{ gap: 18, marginBottom: 12, fontSize: 12, color: "var(--text-muted)", flexWrap: "wrap" }}
        >
          {retrieval.retrieved_count !== undefined && (
            <span>
              <span style={{ color: "var(--text-faint)" }}>retrieved</span>{" "}
              <span className="evo-mono" style={{ color: "var(--text)" }}>
                {retrieval.retrieved_count}
              </span>
            </span>
          )}
          {retrieval.limit !== undefined && (
            <span>
              <span style={{ color: "var(--text-faint)" }}>limit</span>{" "}
              <span className="evo-mono">{retrieval.limit}</span>
            </span>
          )}
          {retrieval.total_available !== undefined && (
            <span>
              <span style={{ color: "var(--text-faint)" }}>available</span>{" "}
              <span className="evo-mono">{retrieval.total_available}</span>
            </span>
          )}
          {docCount > 0 && (
            <span>
              <span style={{ color: "var(--text-faint)" }}>docs</span>{" "}
              <span className="evo-mono">{docCount}</span>
            </span>
          )}
          {chunkCount > 0 && (
            <span>
              <span style={{ color: "var(--text-faint)" }}>chunks</span>{" "}
              <span className="evo-mono">{chunkCount}</span>
            </span>
          )}
        </div>

        {retrieval.chunk_refs && retrieval.chunk_refs.length > 0 ? (
          <table
            className="evo-table"
            style={{ width: "100%", fontSize: 12 }}
            data-testid="retrieval-chunks-table"
          >
            <thead>
              <tr>
                <th style={{ padding: "6px 8px" }}>chunk_ref</th>
                <th style={{ padding: "6px 8px" }}>doc_ref</th>
                <th style={{ padding: "6px 8px", textAlign: "right" }}>score</th>
              </tr>
            </thead>
            <tbody>
              {retrieval.chunk_refs.slice(0, MAX_ROWS).map((c, i) => (
                <tr key={`${c.chunk_ref ?? "row"}-${i}`}>
                  <td style={{ padding: "6px 8px" }}>
                    <span className="evo-mono" title={c.chunk_ref}>
                      {shortRef(c.chunk_ref)}
                    </span>
                  </td>
                  <td style={{ padding: "6px 8px" }}>
                    <span className="evo-mono" style={{ color: "var(--text-muted)" }} title={c.doc_ref}>
                      {shortRef(c.doc_ref)}
                    </span>
                  </td>
                  <td style={{ padding: "6px 8px", textAlign: "right" }}>
                    <span className="evo-mono">{formatScore(c.score, 3)}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p style={{ margin: 0, fontSize: 12, color: "var(--text-muted)" }}>
            Sem chunk_refs registrados.
          </p>
        )}
        {retrieval.chunk_refs && retrieval.chunk_refs.length > MAX_ROWS && (
          <p style={{ margin: "10px 0 0", fontSize: 11, color: "var(--text-faint)" }}>
            +{retrieval.chunk_refs.length - MAX_ROWS} chunks adicionais não exibidos.
          </p>
        )}
      </div>
    </div>
  );
}
