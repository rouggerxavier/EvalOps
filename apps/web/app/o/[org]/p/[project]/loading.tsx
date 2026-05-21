function MetricSkeleton() {
  return (
    <div className="evo-metric" style={{ minHeight: 112 }}>
      <div style={{ height: 10, width: "40%", borderRadius: 4, background: "var(--bg-2)", marginBottom: 12 }} />
      <div style={{ height: 22, width: "60%", borderRadius: 4, background: "var(--bg-2)", marginBottom: 10 }} />
      <div style={{ height: 9, width: "70%", borderRadius: 4, background: "var(--bg-2)" }} />
    </div>
  );
}

function RowSkeleton() {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: ".2fr 1.4fr .9fr",
        gap: 12,
        padding: "10px 16px",
        borderBottom: "1px solid var(--border-subtle)",
      }}
    >
      <div style={{ height: 18, borderRadius: 4, background: "var(--bg-2)" }} />
      <div style={{ height: 10, borderRadius: 4, background: "var(--bg-2)" }} />
      <div style={{ height: 10, borderRadius: 4, background: "var(--bg-2)" }} />
    </div>
  );
}

export default function Loading() {
  return (
    <div className="evo-page" aria-busy="true" aria-live="polite">
      <div className="evo-page-header">
        <div>
          <p className="evo-page-header__eyebrow">Operação · Overview</p>
          <h1 className="evo-page-header__title">Carregando overview...</h1>
          <p className="evo-page-header__subtitle">Resolvendo projeto, traces e runs de avaliação.</p>
        </div>
      </div>

      <section className="evo-kpi-grid" aria-hidden="true">
        {Array.from({ length: 5 }).map((_, idx) => (
          <MetricSkeleton key={idx} />
        ))}
      </section>

      <section className="evo-overview-main-grid" style={{ marginTop: 16 }} aria-hidden="true">
        <div className="evo-overview-card">
          <div className="evo-card__header">
            <div style={{ height: 14, width: 140, borderRadius: 4, background: "var(--bg-2)" }} />
          </div>
          <div className="evo-overview-list">
            {Array.from({ length: 5 }).map((_, idx) => (
              <RowSkeleton key={idx} />
            ))}
          </div>
        </div>
        <div className="evo-overview-card">
          <div className="evo-card__header">
            <div style={{ height: 14, width: 140, borderRadius: 4, background: "var(--bg-2)" }} />
          </div>
          <div className="evo-overview-list">
            {Array.from({ length: 5 }).map((_, idx) => (
              <RowSkeleton key={idx} />
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}
