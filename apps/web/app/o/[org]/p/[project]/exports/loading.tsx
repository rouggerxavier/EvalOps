function RowSkeleton() {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "1.5fr .6fr .6fr .8fr .8fr .9fr .7fr .9fr",
        gap: 12,
        padding: "10px 16px",
        borderBottom: "1px solid var(--border-subtle)",
      }}
    >
      {Array.from({ length: 8 }).map((_, idx) => (
        <div key={idx} style={{ height: 10, borderRadius: 4, background: "var(--bg-2)" }} />
      ))}
    </div>
  );
}

export default function Loading() {
  return (
    <div className="evo-page">
      <div className="evo-page-header">
        <div>
          <h1 className="evo-page-header__title">Exports</h1>
          <p className="evo-page-header__subtitle">Carregando jobs de export...</p>
        </div>
      </div>

      <section className="evo-card">
        <div className="evo-card__header">
          <h3 className="evo-card__title">Jobs de export</h3>
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

