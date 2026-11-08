import Link from "next/link";
import { CheckCircle2, CircleMinus, TriangleAlert } from "lucide-react";

import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { createExportAction } from "@/lib/actions";
import {
  getExport,
  getExportDownloadPath,
  hasAuthToken,
  listExports,
  resolveProject,
} from "@/lib/api";
import { formatBytes, formatCount } from "@/lib/format";
import { safeErrorMessage } from "@/lib/safe-error";
import type { ExportJob } from "@/lib/types";

type Props = {
  params: Promise<{ org: string; project: string }>;
  searchParams: Promise<{ export_id?: string; ids?: string; cursor?: string; created?: string; error?: string }>;
};

type ExportRow = { id: string; job: ExportJob | null; error: string | null };

const fieldLabels: Record<string, string> = {
  prod: "Produção",
  staging: "Staging",
  dev: "Dev",
  ok: "Aprovado",
  partial: "Parcial",
  error: "Reprovado",
};

function queryString(values: Record<string, string | undefined>): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) if (value) query.set(key, value);
  return query.toString() ? `?${query.toString()}` : "";
}

function parseExportIds(singleId?: string, idsCsv?: string): string[] {
  return Array.from(new Set([singleId ?? "", ...(idsCsv ?? "").split(",")]
    .map((value) => value.trim())
    .filter(Boolean))).slice(0, 20);
}

function relTime(iso: string): string {
  const minutes = Math.floor((Date.now() - Date.parse(iso)) / 60_000);
  if (minutes < 1) return "agora";
  if (minutes < 60) return `${minutes} min atrás`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} h atrás`;
  return `${Math.floor(hours / 24)} d atrás`;
}

function statusOf(job: ExportJob): "ready" | "running" | "failed" | "expired" | "unknown" {
  if (job.expires_at && Date.parse(job.expires_at) <= Date.now()) return "expired";
  const status = job.status.toLowerCase();
  if (status === "completed" || status === "ready") return "ready";
  if (status === "running" || status === "queued") return "running";
  if (status === "failed" || status === "error") return "failed";
  return "unknown";
}

function statusLabel(status: ReturnType<typeof statusOf>): string {
  if (status === "ready") return "Pronto";
  if (status === "running") return "Gerando";
  if (status === "failed") return "Falhou";
  if (status === "expired") return "Expirado";
  return "Sem dados";
}

function ExportStatus({ status }: { status: ReturnType<typeof statusOf> }) {
  if (status === "ready") {
    return <span className="badge badge--ok"><CheckCircle2 size={13} aria-hidden="true" /> Pronto</span>;
  }
  if (status === "running") {
    return <span className="badge"><CircleMinus size={13} aria-hidden="true" /> Gerando</span>;
  }
  if (status === "failed") {
    return <span className="badge badge--err"><TriangleAlert size={13} aria-hidden="true" /> Falhou</span>;
  }
  if (status === "expired") {
    return <span className="badge"><CircleMinus size={13} aria-hidden="true" /> Expirado</span>;
  }
  return <span className="badge">Sem dados</span>;
}

function filterLabel(filters: Record<string, unknown>): string {
  const values: string[] = [];
  const environment = filters.environment;
  const status = filters.status;
  const name = filters.name_contains;
  if (typeof environment === "string") values.push(fieldLabels[environment] ?? environment);
  else values.push("Todos os ambientes");
  if (typeof status === "string") values.push(`situação ${fieldLabels[status] ?? status}`);
  if (typeof name === "string" && name) values.push(`nome contém ${name}`);
  return values.join(" · ");
}

export default async function ExportsPage({ params, searchParams }: Props) {
  const { org, project } = await params;
  const qp = await searchParams;

  if (!(await hasAuthToken())) return <AuthRequiredPanel layout="main" />;

  const basePath = `/o/${org}/p/${project}/exports`;
  const ids = parseExportIds(qp.export_id, qp.ids);
  const idsValue = ids.join(",");
  let resolvedProject: Awaited<ReturnType<typeof resolveProject>>;
  try {
    resolvedProject = await resolveProject(org, project);
  } catch (error) {
    return (
      <div className="page">
        <header className="page-header">
          <div>
            <h1 className="page-header__title">Exports</h1>
            <p className="page-header__subtitle">Baixe traces em JSONL para analisar fora do EvalOps.</p>
          </div>
        </header>
        <section className="card ops-empty" role="alert">
          <div><h2>Projeto indisponível</h2><p>{safeErrorMessage(error, "Falha ao resolver projeto.")}</p></div>
        </section>
      </div>
    );
  }

  const [listResult, knownRows] = await Promise.all([
    listExports(resolvedProject.project_id, 50, qp.cursor)
      .then((result) => ({ data: result.data, nextCursor: result.next_cursor, error: null as string | null }))
      .catch((error) => ({ data: [] as ExportJob[], nextCursor: null, error: safeErrorMessage(error, "Falha ao carregar exports.") })),
    Promise.all(ids.map(async (id): Promise<ExportRow> => {
      try {
        return { id, job: await getExport(id), error: null };
      } catch (error) {
        return { id, job: null, error: safeErrorMessage(error, "Falha ao consultar export.") };
      }
    })),
  ]);

  const serverIds = new Set(listResult.data.map((job) => job.id));
  const rows: ExportRow[] = [
    ...listResult.data.map((job) => ({ id: job.id, job, error: null })),
    ...knownRows.filter((row) => !serverIds.has(row.id)),
  ];
  const returnPath = `${basePath}${queryString({ ids: idsValue || undefined, cursor: qp.cursor })}`;

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1 className="page-header__title">Exports</h1>
          <p className="page-header__subtitle">
            Baixe traces em JSONL para analisar fora do EvalOps. O arquivo expira depois de 7 dias.
          </p>
        </div>
      </header>

      {qp.error ? <p className="ops-note" role="alert">{safeErrorMessage(qp.error, "Falha ao criar export.")}</p> : null}
      {qp.created ? <p className="ops-note" role="status">Export criado.</p> : null}
      {listResult.error ? <p className="ops-note" role="alert">{listResult.error}</p> : null}

      <section className="card">
        <div className="card__header"><h2 className="card__title">Criar export</h2></div>
        <form action={createExportAction} className="ops-form ops-form__grid">
          <input type="hidden" name="org" value={org} />
          <input type="hidden" name="project" value={project} />
          <input type="hidden" name="project_id" value={resolvedProject.project_id} />
          <input type="hidden" name="known_export_ids" value={idsValue} />
          <label className="ops-form__field">
            <span>Ambiente</span>
            <select name="environment" defaultValue="">
              <option value="">Todos</option>
              <option value="prod">Produção</option>
              <option value="staging">Staging</option>
              <option value="dev">Dev</option>
            </select>
          </label>
          <label className="ops-form__field">
            <span>Situação</span>
            <select name="status" defaultValue="">
              <option value="">Todas</option>
              <option value="ok">Aprovado</option>
              <option value="partial">Parcial</option>
              <option value="error">Reprovado</option>
            </select>
          </label>
          <label className="ops-form__field">
            <span>Nome contém</span>
            <input name="name_contains" placeholder="checkout" />
          </label>
          <button type="submit" className="btn btn--primary">Criar export</button>
        </form>
      </section>

      <section className="card">
        <div className="card__header"><h2 className="card__title">Exports recentes</h2></div>
        <div className="table-wrap">
          <table className="t">
            <thead>
              <tr>
                <th>Situação</th>
                <th>Filtro</th>
                <th className="t__num">Linhas</th>
                <th className="t__num">Tamanho</th>
                <th className="t__num">Criado</th>
                <th>Ações</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr><td className="empty-row" colSpan={6}>Sem dados. Crie um export para baixar traces.</td></tr>
              ) : rows.map((row) => {
                if (!row.job) {
                  return (
                  <tr key={row.id}>
                      <td><span className="badge">Sem dados</span></td>
                      <td title={row.error ?? undefined}>Sem dados</td>
                      <td className="t__num">Sem dados</td>
                      <td className="t__num">Sem dados</td>
                      <td className="t__num">Sem dados</td>
                      <td>Sem dados</td>
                    </tr>
                  );
                }
                const status = statusOf(row.job);
                const canDownload = status === "ready" && Boolean(row.job.file_path);
                const canRetry = status === "failed" || status === "expired";
                return (
                  <tr key={row.id}>
                    <td><ExportStatus status={status} /></td>
                    <td>{filterLabel(row.job.filters)}</td>
                    <td className="t__num">{formatCount(row.job.row_count)}</td>
                    <td className="t__num">{row.job.file_size_bytes === null ? "Sem dados" : formatBytes(row.job.file_size_bytes)}</td>
                    <td className="t__num">{relTime(row.job.created_at)}</td>
                    <td>
                      {canDownload ? (
                        <Link className="btn btn--sm" href={getExportDownloadPath(row.job.id, returnPath)} download>Baixar</Link>
                      ) : canRetry ? (
                        <form action={createExportAction}>
                          <input type="hidden" name="org" value={org} />
                          <input type="hidden" name="project" value={project} />
                          <input type="hidden" name="project_id" value={resolvedProject.project_id} />
                          <input type="hidden" name="known_export_ids" value={idsValue} />
                          <input type="hidden" name="environment" value={typeof row.job.filters.environment === "string" ? row.job.filters.environment : ""} />
                          <input type="hidden" name="status" value={typeof row.job.filters.status === "string" ? row.job.filters.status : ""} />
                          <input type="hidden" name="name_contains" value={typeof row.job.filters.name_contains === "string" ? row.job.filters.name_contains : ""} />
                          <button type="submit" className="btn btn--sm">Refazer</button>
                        </form>
                      ) : (
                        <button type="button" className="btn btn--sm" disabled>{statusLabel(status)}</button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {listResult.nextCursor ? (
          <div className="card__body">
            <Link className="btn" href={`${basePath}${queryString({ ids: idsValue || undefined, cursor: listResult.nextCursor })}`}>
              Mais exports
            </Link>
          </div>
        ) : null}
      </section>
    </div>
  );
}
