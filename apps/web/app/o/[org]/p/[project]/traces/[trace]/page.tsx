import Link from "next/link";

import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { getTrace, hasAuthToken } from "@/lib/api";
import { createTraceFeedbackAction } from "@/lib/actions";

type Props = {
  params: Promise<{ org: string; project: string; trace: string }>;
  searchParams: Promise<{ feedback?: string; error?: string }>;
};

function prettyJson(value: unknown): string {
  if (!value) return "-";
  return JSON.stringify(value, null, 2);
}

export default async function TraceDetailPage({ params, searchParams }: Props) {
  const { org, project, trace } = await params;
  const qp = await searchParams;

  if (!(await hasAuthToken())) {
    return <AuthRequiredPanel layout="container" />;
  }

  const detail = await getTrace(trace);
  const traceRow = detail.trace;

  return (
    <main className="container">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <h1 style={{ margin: 0 }}>{traceRow.name}</h1>
          <p className="muted" style={{ marginTop: 8 }}>
            Trace ID: {traceRow.id}
          </p>
        </div>
        <div className="row">
          <span className={`badge status-${traceRow.status}`}>{traceRow.status}</span>
          <Link href={`/o/${org}/p/${project}/traces`}>Voltar</Link>
        </div>
      </div>

      <section className="grid-4" style={{ marginTop: 12 }}>
        <div className="panel">
          <div className="muted">DuraÃ§Ã£o</div>
          <div className="kpi">{traceRow.duration_ms}ms</div>
        </div>
        <div className="panel">
          <div className="muted">Tokens in/out</div>
          <div className="kpi" style={{ fontSize: 22 }}>
            {traceRow.total_tokens_in}/{traceRow.total_tokens_out}
          </div>
        </div>
        <div className="panel">
          <div className="muted">Custo USD</div>
          <div className="kpi">{traceRow.total_cost_usd.toFixed(6)}</div>
        </div>
        <div className="panel">
          <div className="muted">Eventos</div>
          <div className="kpi">{detail.events_count}</div>
        </div>
      </section>

      <section className="panel" style={{ marginTop: 12 }}>
        <h3 style={{ marginTop: 0 }}>Spans</h3>
        {detail.spans.length === 0 ? (
          <p className="muted">Sem spans neste trace.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Span</th>
                <th>Tipo</th>
                <th>Status</th>
                <th>Model</th>
                <th>DuraÃ§Ã£o</th>
                <th>Eventos</th>
              </tr>
            </thead>
            <tbody>
              {detail.spans.map((span) => (
                <tr key={span.id}>
                  <td>{span.name}</td>
                  <td>{span.type}</td>
                  <td className={span.status === "ok" ? "status-ok" : "status-error"}>{span.status}</td>
                  <td>{span.model ?? "-"}</td>
                  <td>{span.duration_ms}ms</td>
                  <td>{span.events.length}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="panel" style={{ marginTop: 12 }}>
        <h3 style={{ marginTop: 0 }}>Feedback humano</h3>
        {qp.feedback === "1" ? <p className="ok">Feedback registrado.</p> : null}
        {qp.error ? <p className="error">{qp.error}</p> : null}

        <form action={createTraceFeedbackAction} className="grid-2" style={{ marginTop: 8 }}>
          <input type="hidden" name="org" value={org} />
          <input type="hidden" name="project" value={project} />
          <input type="hidden" name="trace_id" value={traceRow.id} />
          <label>
            Thumbs
            <select name="thumbs" defaultValue="up">
              <option value="up">up</option>
              <option value="down">down</option>
            </select>
          </label>
          <label>
            ComentÃ¡rio
            <input name="comment" placeholder="o que aconteceu neste trace?" />
          </label>
          <button type="submit">Enviar feedback</button>
        </form>

        <div style={{ marginTop: 12 }}>
          {detail.feedback.length === 0 ? (
            <p className="muted">Sem feedback para este trace.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Thumbs</th>
                  <th>ComentÃ¡rio</th>
                  <th>Source</th>
                  <th>Data</th>
                </tr>
              </thead>
              <tbody>
                {detail.feedback.map((fb) => (
                  <tr key={fb.id}>
                    <td>{fb.thumbs ?? "-"}</td>
                    <td>{fb.comment ?? "-"}</td>
                    <td>{fb.source}</td>
                    <td>{new Date(fb.created_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>

      <section className="grid-2" style={{ marginTop: 12 }}>
        <div className="panel">
          <h3 style={{ marginTop: 0 }}>Trace metadata</h3>
          <pre style={{ overflow: "auto", margin: 0 }}>{prettyJson(traceRow.metadata)}</pre>
        </div>
        <div className="panel">
          <h3 style={{ marginTop: 0 }}>Primeiro span (raw)</h3>
          <pre style={{ overflow: "auto", margin: 0 }}>
            {detail.spans.length > 0 ? prettyJson(detail.spans[0]) : "-"}
          </pre>
        </div>
      </section>
    </main>
  );
}



