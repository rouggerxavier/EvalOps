import type { CitationRefs } from "@/lib/rag";
import { shortRef } from "@/lib/rag";

type Props = { citations: CitationRefs };

const MAX_ROWS = 12;

export function CitationRefsTable({ citations }: Props) {
  const rows = citations.items;

  return (
    <div className="evo-card" data-testid="citation-refs-table">
      <div className="evo-card__header">
        <h3 className="evo-card__title">Citações</h3>
        <div className="evo-row" style={{ gap: 6 }}>
          <span className="evo-tag">{rows.length}</span>
          {citations.truncated && (
            <span className="evo-badge evo-badge--warn">
              <span className="evo-badge__dot" /> truncado
            </span>
          )}
        </div>
      </div>
      <div className="evo-card__body" style={{ padding: 0 }}>
        <table className="evo-table" style={{ fontSize: 12 }}>
          <thead>
            <tr>
              <th style={{ padding: "6px 12px", width: 56 }}>fonte</th>
              <th style={{ padding: "6px 12px" }}>chunk_ref</th>
              <th style={{ padding: "6px 12px" }}>doc_ref</th>
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, MAX_ROWS).map((c, i) => (
              <tr key={`${c.chunk_ref ?? "cit"}-${i}`}>
                <td style={{ padding: "6px 12px" }}>
                  <span className="evo-mono">{c.fonte_n ?? i + 1}</span>
                </td>
                <td style={{ padding: "6px 12px" }}>
                  <span className="evo-mono" title={c.chunk_ref}>
                    {shortRef(c.chunk_ref)}
                  </span>
                </td>
                <td style={{ padding: "6px 12px" }}>
                  <span
                    className="evo-mono"
                    style={{ color: "var(--text-muted)" }}
                    title={c.doc_ref}
                  >
                    {shortRef(c.doc_ref)}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length > MAX_ROWS && (
          <p
            style={{
              margin: 0,
              padding: "10px 12px",
              fontSize: 11,
              color: "var(--text-faint)",
              borderTop: "1px solid var(--border-subtle)",
            }}
          >
            +{rows.length - MAX_ROWS} citações adicionais não exibidas.
          </p>
        )}
        {(citations.limit !== undefined || citations.total_available !== undefined) && (
          <p
            style={{
              margin: 0,
              padding: "8px 12px",
              fontSize: 11,
              color: "var(--text-muted)",
              borderTop: "1px solid var(--border-subtle)",
            }}
          >
            {citations.limit !== undefined && (
              <>
                limit <span className="evo-mono">{citations.limit}</span>
              </>
            )}
            {citations.limit !== undefined && citations.total_available !== undefined && " · "}
            {citations.total_available !== undefined && (
              <>
                available <span className="evo-mono">{citations.total_available}</span>
              </>
            )}
          </p>
        )}
      </div>
    </div>
  );
}
