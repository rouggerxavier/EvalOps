function RowSkeleton() {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "1.6fr .6fr .6fr .8fr",
        gap: 12,
        padding: "10px 16px",
        borderBottom: "1px solid var(--border-subtle)",
      }}
    >
      {Array.from({ length: 4 }).map((_, idx) => (
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
          <p className="evo-page-header__eyebrow">Recursos · Prompts</p>
          <h1 className="evo-page-header__title">Carregando prompts...</h1>
          <p className="evo-page-header__subtitle">Lendo templates e versões cadastrados.</p>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <section className="evo-card">
          <div className="evo-card__header">
            <div style={{ height: 14, width: 100, borderRadius: 4, background: "var(--bg-2)" }} />
          </div>
          <div className="evo-card__body" style={{ padding: 0 }}>
            {Array.from({ length: 6 }).map((_, idx) => (
              <RowSkeleton key={idx} />
            ))}
          </div>
        </section>

        <section className="evo-card">
          <div className="evo-card__header">
            <div style={{ height: 14, width: 140, borderRadius: 4, background: "var(--bg-2)" }} />
          </div>
          <div className="evo-card__body" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div style={{ height: 12, width: "80%", borderRadius: 4, background: "var(--bg-2)" }} />
            <div style={{ height: 12, width: "60%", borderRadius: 4, background: "var(--bg-2)" }} />
            <div style={{ height: 12, width: "90%", borderRadius: 4, background: "var(--bg-2)" }} />
            <div style={{ height: 12, width: "70%", borderRadius: 4, background: "var(--bg-2)" }} />
          </div>
        </section>
      </div>
    </div>
  );
}
