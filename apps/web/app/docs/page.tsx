const RAW_API_BASE = process.env.EVALOPS_API_BASE_URL ?? "http://localhost:8000/v1";
const API_ROOT = RAW_API_BASE.endsWith("/v1") ? RAW_API_BASE.slice(0, -3) : RAW_API_BASE;

export default function DocsPage() {
  return (
    <main className="container">
      <div className="panel">
        <h1 style={{ marginTop: 0 }}>Documentation</h1>
        <p className="muted">
          EvalOps combines implementation in this repo with the spec set in <code>/docs</code>.
        </p>
        <ul>
          <li>
            <a href={`${API_ROOT}/docs`} target="_blank" rel="noreferrer">
              API OpenAPI (FastAPI /docs)
            </a>
          </li>
          <li>
            <a href={`${API_ROOT}/openapi.json`} target="_blank" rel="noreferrer">
              Raw OpenAPI JSON
            </a>
          </li>
        </ul>
      </div>
    </main>
  );
}
