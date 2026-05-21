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
        gridTemplateColumns: "1.3fr .8fr .7fr .9fr .8fr",
        gap: 12,
        padding: "10px 16px",
        borderBottom: "1px solid var(--border-subtle)",
      }}
    >
      {Array.from({ length: 5 }).map((_, idx) => (
        <div key={idx} style={{ height: 10, borderRadius: 4, background: "var(--bg-2)" }} />
      ))}
    </div>
  );
}

export default function Loading() {
  return (
    <div className="evo-page" aria-busy="true" aria-live="polite">
      <div className="evo-page-header">
        <div>
          <p className="evo-page-header__eyebrow">Operação · Avaliações</p>
          <h1 className="evo-page-header__title">Carregando avaliações...</h1>
          <p className="evo-page-header__subtitle">Buscando rubricas, runs e distribuições.</p>
        </div>
      </div>

      <section className="evo-kpi-grid" aria-hidden="true">
        {Array.from({ length: 4 }).map((_, idx) => (
          <MetricSkeleton key={idx} />
        ))}
      </section>

      <section className="evo-card" style={{ marginTop: 16 }}>
        <div className="evo-card__header">
          <div style={{ height: 14, width: 160, borderRadius: 4, background: "var(--bg-2)" }} />
        </div>
        <div className="evo-card__body" style={{ padding: 0 }}>
          {Array.from({ length: 6 }).map((_, idx) => (
            <RowSkeleton key={idx} />
          ))}
        </div>
      </section>
    </div>
  );
}
