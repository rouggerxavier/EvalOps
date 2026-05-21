function RowSkeleton() {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "1.4fr .8fr .8fr 1fr .6fr .6fr .8fr",
        gap: 12,
        padding: "10px 16px",
        borderBottom: "1px solid var(--border-subtle)",
      }}
    >
      {Array.from({ length: 7 }).map((_, idx) => (
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
          <p className="evo-page-header__eyebrow">Recursos · Experimentos</p>
          <h1 className="evo-page-header__title">Carregando experimentos...</h1>
          <p className="evo-page-header__subtitle">Lendo variantes, datasets e rubricas.</p>
        </div>
      </div>

      <section className="evo-card">
        <div className="evo-card__header">
          <div style={{ height: 14, width: 140, borderRadius: 4, background: "var(--bg-2)" }} />
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
