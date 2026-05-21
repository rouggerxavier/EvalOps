function MetricSkeleton() {
  return (
    <div className="evo-metric" style={{ minHeight: 100 }}>
      <div style={{ height: 9, width: "45%", borderRadius: 4, background: "var(--bg-2)", marginBottom: 10 }} />
      <div style={{ height: 20, width: "65%", borderRadius: 4, background: "var(--bg-2)", marginBottom: 8 }} />
      <div style={{ height: 9, width: "55%", borderRadius: 4, background: "var(--bg-2)" }} />
    </div>
  );
}

export default function Loading() {
  return (
    <div className="evo-page" aria-busy="true" aria-live="polite">
      <div className="evo-page-header">
        <div>
          <p className="evo-page-header__eyebrow">Operação · Trace detail</p>
          <h1 className="evo-page-header__title">Carregando trace...</h1>
          <p className="evo-page-header__subtitle">Recuperando spans, RAG e feedback humano.</p>
        </div>
      </div>

      <section className="evo-kpi-grid" aria-hidden="true">
        {Array.from({ length: 5 }).map((_, idx) => (
          <MetricSkeleton key={idx} />
        ))}
      </section>

      <section className="evo-card" style={{ marginTop: 16 }} aria-hidden="true">
        <div className="evo-card__body" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ height: 14, width: "60%", borderRadius: 4, background: "var(--bg-2)" }} />
          <div style={{ height: 10, width: "100%", borderRadius: 4, background: "var(--bg-2)" }} />
          <div style={{ height: 10, width: "90%", borderRadius: 4, background: "var(--bg-2)" }} />
          <div style={{ height: 10, width: "70%", borderRadius: 4, background: "var(--bg-2)" }} />
        </div>
      </section>
    </div>
  );
}
