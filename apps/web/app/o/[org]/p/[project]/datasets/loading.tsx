function RowSkeleton() {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "1.6fr .9fr .6fr .7fr .9fr .3fr",
        gap: 12,
        padding: "10px 16px",
        borderBottom: "1px solid var(--border-subtle)",
      }}
    >
      <div style={{ height: 10, borderRadius: 4, background: "var(--bg-2)" }} />
      <div style={{ height: 10, borderRadius: 4, background: "var(--bg-2)" }} />
      <div style={{ height: 10, borderRadius: 4, background: "var(--bg-2)" }} />
      <div style={{ height: 10, borderRadius: 4, background: "var(--bg-2)" }} />
      <div style={{ height: 10, borderRadius: 4, background: "var(--bg-2)" }} />
      <div style={{ height: 10, borderRadius: 4, background: "var(--bg-2)" }} />
    </div>
  );
}

export default function Loading() {
  return (
    <div className="evo-page">
      <div className="evo-page-header">
        <div>
          <p className="evo-page-header__eyebrow">Dados · Datasets</p>
          <h1 className="evo-page-header__title">Datasets</h1>
          <p className="evo-page-header__subtitle">Carregando datasets do projeto...</p>
        </div>
      </div>

      <section className="evo-card">
        <div className="evo-card__header">
          <h3 className="evo-card__title">Lista de datasets</h3>
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

