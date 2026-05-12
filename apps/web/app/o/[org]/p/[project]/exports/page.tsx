import Link from "next/link";

import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { createExportAction } from "@/lib/actions";
import {
  getExport,
  getOrganizationSubscription,
  getOrganizationUsage,
  hasAuthToken,
  resolveProject,
} from "@/lib/api";

type Props = {
  params: Promise<{ org: string; project: string }>;
  searchParams: Promise<{ created?: string; export_id?: string; error?: string }>;
};

export default async function ExportsPage({ params, searchParams }: Props) {
  const { org, project } = await params;
  const qp = await searchParams;

  if (!(await hasAuthToken())) {
    return <AuthRequiredPanel layout="container" />;
  }

  const resolved = await resolveProject(org, project);
  const usage = await getOrganizationUsage(resolved.org_id);
  const sub = await getOrganizationSubscription(resolved.org_id);
  const exportJob = qp.export_id ? await getExport(qp.export_id) : null;

  return (
    <main className="container">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h1 style={{ margin: 0 }}>Exports</h1>
        <Link href={`/o/${org}/p/${project}`}>Voltar ao overview</Link>
      </div>

      {qp.created === "1" ? <p className="ok">Export criado com sucesso.</p> : null}
      {qp.error ? <p className="error">{qp.error}</p> : null}

      <section className="grid-2" style={{ marginTop: 12 }}>
        <div className="panel">
          <h3 style={{ marginTop: 0 }}>Criar export JSONL</h3>
          <form action={createExportAction} className="grid-2">
            <input type="hidden" name="org" value={org} />
            <input type="hidden" name="project" value={project} />
            <input type="hidden" name="project_id" value={resolved.project_id} />
            <label>
              Environment
              <select name="environment" defaultValue="">
                <option value="">todos</option>
                <option value="dev">dev</option>
                <option value="staging">staging</option>
                <option value="prod">prod</option>
              </select>
            </label>
            <label>
              Status
              <select name="status" defaultValue="">
                <option value="">todos</option>
                <option value="ok">ok</option>
                <option value="partial">partial</option>
                <option value="error">error</option>
              </select>
            </label>
            <button type="submit">Gerar export</button>
          </form>
        </div>

        <div className="panel">
          <h3 style={{ marginTop: 0 }}>Plano e uso</h3>
          <p className="muted" style={{ marginBottom: 8 }}>
            Plano: <strong>{sub.plan.name}</strong> ({sub.plan.code})
          </p>
          <p style={{ margin: "6px 0" }}>Traces: {usage.traces_ingested}/{sub.plan.monthly_trace_limit}</p>
          <p style={{ margin: "6px 0" }}>Evals: {usage.evaluations_run}/{sub.plan.monthly_eval_limit}</p>
          <p style={{ margin: "6px 0" }}>Exports: {usage.exports_created}/{sub.plan.monthly_export_limit}</p>
          <p style={{ margin: "6px 0" }}>Custo (USD): {usage.cost_usd.toFixed(6)}</p>
        </div>
      </section>

      <section className="panel" style={{ marginTop: 12 }}>
        <h3 style={{ marginTop: 0 }}>Ãšltimo export consultado</h3>
        {exportJob ? (
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Status</th>
                <th>Rows</th>
                <th>Arquivo</th>
                <th>Criado em</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>{exportJob.id}</td>
                <td>{exportJob.status}</td>
                <td>{exportJob.row_count}</td>
                <td>{exportJob.file_path ?? "-"}</td>
                <td>{new Date(exportJob.created_at).toLocaleString()}</td>
              </tr>
            </tbody>
          </table>
        ) : (
          <p className="muted">Crie um export para ver os detalhes aqui.</p>
        )}
      </section>
    </main>
  );
}



