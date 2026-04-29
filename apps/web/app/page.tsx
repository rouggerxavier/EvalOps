export default function HomePage() {
  return (
    <main className="container">
      <div className="panel">
        <h1 style={{ marginTop: 0 }}>EvalOps Studio</h1>
        <p className="muted">
          Fase 3 iniciada: dashboard de traces com overview, listagem e detalhe.
        </p>
        <p>
          Abra um projeto em{" "}
          <a href="/o/demo-org/p/demo-project">/o/demo-org/p/demo-project</a>.
        </p>
        <p className="muted" style={{ marginBottom: 0 }}>
          Requer variáveis: <code>EVALOPS_API_BASE_URL</code> e{" "}
          <code>EVALOPS_DASHBOARD_BEARER_TOKEN</code>.
        </p>
      </div>
    </main>
  );
}
