import Link from "next/link";

import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { EnvBadge, Flash, StatusBadge } from "@/components/ui";
import { createExportAction } from "@/lib/actions";
import {
  getExport,
  getOrganizationSubscription,
  getOrganizationUsage,
  hasAuthToken,
  resolveProject,
} from "@/lib/api";
import { formatCost, formatDateTime, formatCount } from "@/lib/format";

type Props = {
  params: Promise<{ org: string; project: string }>;
  searchParams: Promise<{ created?: string; export_id?: string; error?: string }>;
};

function percent(value: number, limit: number): number {
  if (!limit || limit <= 0) return 0;
  return Math.min(100, (value / limit) * 100);
}

function UsageMetric({
  label,
  value,
  limit,
}: {
  label: string;
  value: number;
  limit: number;
}) {
  const pct = percent(value, limit);
  return (
    <div className="usage-metric">
      <div className="usage-metric__head">
        <span>{label}</span>
        <span>{formatCount(value)} / {formatCount(limit)}</span>
      </div>
      <div className="usage-metric__bar">
        <i style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export default async function ExportsPage({ params, searchParams }: Props) {
  const { org, project } = await params;
  const qp = await searchParams;

  if (!(await hasAuthToken())) {
    return <AuthRequiredPanel layout="main" />;
  }

  const resolved = await resolveProject(org, project);
  const [usage, sub, exportJob] = await Promise.all([
    getOrganizationUsage(resolved.org_id),
    getOrganizationSubscription(resolved.org_id),
    qp.export_id ? getExport(qp.export_id) : Promise.resolve(null),
  ]);

  return (
    <main className="main">
      <div className="page-header">
        <div>
          <h1>Exports</h1>
          <p className="sub">Crie exports JSONL para datasets, fine-tuning e análise offline.</p>
        </div>
        <Link className="subtle-link" href={`/o/${org}/p/${project}`}>
          Voltar para visão geral
        </Link>
      </div>

      {qp.created === "1" ? <Flash kind="success" message="Export criado." /> : null}
      {qp.error ? <Flash kind="error" message={qp.error} /> : null}

      <div className="content-grid">
        <section className="card">
          <div className="section-head">
            <div>
              <h2>Criar export JSONL</h2>
              <p>Filtre traces por ambiente e status antes de criar o job.</p>
            </div>
          </div>

          <form action={createExportAction} className="stack-form">
            <input type="hidden" name="org" value={org} />
            <input type="hidden" name="project" value={project} />
            <input type="hidden" name="project_id" value={resolved.project_id} />
            <label className="field">
              <span>Ambiente</span>
              <select name="environment" defaultValue="">
                <option value="">Todos os ambientes</option>
                <option value="dev">dev</option>
                <option value="staging">staging</option>
                <option value="prod">prod</option>
              </select>
            </label>
            <label className="field">
              <span>Status</span>
              <select name="status" defaultValue="">
                <option value="">Todos os status</option>
                <option value="ok">ok</option>
                <option value="partial">partial</option>
                <option value="error">error</option>
              </select>
            </label>
            <button type="submit" className="primary-btn">Gerar export</button>
          </form>
        </section>

        <section className="card">
          <div className="section-head">
            <div>
              <h2>Plano e uso</h2>
              <p>{sub.plan.name} ({sub.plan.code})</p>
            </div>
          </div>

          <div className="billing-amount">{formatCost(usage.cost_usd)}</div>
          <div className="billing-meta">Uso registrado no período {usage.period}</div>

          <div className="usage-metrics" style={{ marginTop: 16 }}>
            <UsageMetric label="Traces" value={usage.traces_ingested} limit={sub.plan.monthly_trace_limit} />
            <UsageMetric label="Avaliações" value={usage.evaluations_run} limit={sub.plan.monthly_eval_limit} />
            <UsageMetric label="Exports" value={usage.exports_created} limit={sub.plan.monthly_export_limit} />
          </div>
        </section>
      </div>

      <section className="card table-card">
        <div className="table-head">
          <div className="title">Último export</div>
          {exportJob ? <EnvBadge>{exportJob.format}</EnvBadge> : null}
        </div>

        {exportJob ? (
          <table className="t-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Status</th>
                <th>Linhas</th>
                <th>Arquivo</th>
                <th>Criado em</th>
                <th>Concluído em</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td className="trace-id">{exportJob.id}</td>
                <td><StatusBadge status={exportJob.status}>{exportJob.status}</StatusBadge></td>
                <td>{formatCount(exportJob.row_count)}</td>
                <td className="model">{exportJob.file_path ?? "-"}</td>
                <td>{formatDateTime(exportJob.created_at)}</td>
                <td>{exportJob.completed_at ? formatDateTime(exportJob.completed_at) : "-"}</td>
              </tr>
            </tbody>
          </table>
        ) : (
          <p className="empty-state">Crie um export para ver os detalhes do job aqui.</p>
        )}
      </section>
    </main>
  );
}


