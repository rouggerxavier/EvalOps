import Link from "next/link";

import { getOverview, hasDashboardToken } from "@/lib/api";

type Props = {
  params: Promise<{ org: string; project: string }>;
  searchParams: Promise<{ environment?: string }>;
};

function percent(v: number): string {
  return `${(v * 100).toFixed(1)}%`;
}

export default async function ProjectOverviewPage({ params, searchParams }: Props) {
  const { org, project } = await params;
  const qp = await searchParams;

  if (!hasDashboardToken()) {
    return (
      <main className="container">
        <div className="panel">
          <h2 style={{ marginTop: 0 }}>Configuração pendente</h2>
          <p className="muted">
            Defina <code>EVALOPS_DASHBOARD_BEARER_TOKEN</code> para o dashboard consultar a API.
          </p>
        </div>
      </main>
    );
  }

  const overview = await getOverview(project, qp.environment);
  const env = qp.environment ?? "prod";

  return (
    <main className="container">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <h1 style={{ margin: 0 }}>Projeto: {project}</h1>
          <p className="muted" style={{ marginTop: 6 }}>
            Organização: {org}
          </p>
        </div>
        <div className="row">
          <span className="badge">env: {env}</span>
          <Link href={`/o/${org}/p/${project}/traces`}>Ver traces</Link>
        </div>
      </div>

      <section className="grid-4" style={{ marginTop: 14 }}>
        <div className="panel">
          <div className="muted">Traces</div>
          <div className="kpi">{overview.kpis.traces}</div>
        </div>
        <div className="panel">
          <div className="muted">Custo (USD)</div>
          <div className="kpi">{overview.kpis.cost_usd.toFixed(4)}</div>
        </div>
        <div className="panel">
          <div className="muted">Latência p95</div>
          <div className="kpi">{overview.kpis.latency_p95_ms}ms</div>
        </div>
        <div className="panel">
          <div className="muted">% Erro</div>
          <div className="kpi">{percent(overview.kpis.error_rate)}</div>
        </div>
      </section>

      <section className="grid-2" style={{ marginTop: 12 }}>
        <div className="panel">
          <h3 style={{ marginTop: 0 }}>Custo por dia</h3>
          {overview.cost_by_day.length === 0 ? (
            <p className="muted">Sem dados ainda.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Dia</th>
                  <th>Traces</th>
                  <th>Custo USD</th>
                </tr>
              </thead>
              <tbody>
                {overview.cost_by_day.map((row) => (
                  <tr key={row.day}>
                    <td>{row.day}</td>
                    <td>{row.traces}</td>
                    <td>{row.cost_usd.toFixed(6)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        <div className="panel">
          <h3 style={{ marginTop: 0 }}>Custo por modelo</h3>
          {overview.model_breakdown.length === 0 ? (
            <p className="muted">Sem spans LLM ainda.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Provider</th>
                  <th>Model</th>
                  <th>Calls</th>
                  <th>Custo USD</th>
                </tr>
              </thead>
              <tbody>
                {overview.model_breakdown.map((row) => (
                  <tr key={`${row.provider}:${row.model}`}>
                    <td>{row.provider}</td>
                    <td>{row.model}</td>
                    <td>{row.calls}</td>
                    <td>{row.cost_usd.toFixed(6)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>

      <section className="panel" style={{ marginTop: 12 }}>
        <h3 style={{ marginTop: 0 }}>Últimos traces com problema</h3>
        {overview.recent_flagged.length === 0 ? (
          <p className="muted">Sem traces com erro/partial.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Trace</th>
                <th>Status</th>
                <th>Duração</th>
                <th>Custo USD</th>
              </tr>
            </thead>
            <tbody>
              {overview.recent_flagged.map((trace) => (
                <tr key={trace.id}>
                  <td>
                    <Link href={`/o/${org}/p/${project}/traces/${trace.id}`}>{trace.name}</Link>
                  </td>
                  <td className={`status-${trace.status}`}>{trace.status}</td>
                  <td>{trace.duration_ms}ms</td>
                  <td>{trace.total_cost_usd.toFixed(6)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </main>
  );
}
