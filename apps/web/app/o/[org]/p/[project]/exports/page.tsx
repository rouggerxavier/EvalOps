import Link from "next/link";
import { Download, Plus, RefreshCw } from "lucide-react";

import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { CopyTextButton } from "@/components/CopyTextButton";
import { createExportAction } from "@/lib/actions";
import {
  getExport,
  getOrganizationSubscription,
  getOrganizationUsage,
  hasAuthToken,
  resolveProject,
} from "@/lib/api";
import { formatCost, formatCount, formatDateTime } from "@/lib/format";
import { safeErrorMessage } from "@/lib/safe-error";
import type { ExportJob } from "@/lib/types";

type Props = {
  params: Promise<{ org: string; project: string }>;
  searchParams: Promise<{ tab?: string; created?: string; export_id?: string; ids?: string; error?: string }>;
};

type ExportRow = {
  id: string;
  job: ExportJob | null;
  error: string | null;
};

const INPUT_STYLE: React.CSSProperties = {
  width: "100%",
  background: "var(--bg-2)",
  border: "1px solid var(--border)",
  borderRadius: 6,
  padding: "7px 10px",
  color: "var(--text)",
  fontSize: 13,
};

const LABEL_STYLE: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 4,
  fontSize: 13,
};

function alertStyle(kind: "ok" | "err"): React.CSSProperties {
  if (kind === "ok") {
    return {
      padding: "10px 14px",
      background: "var(--ok-bg)",
      border: "1px solid var(--ok-border)",
      borderRadius: 6,
      color: "var(--ok)",
      fontSize: 13,
      marginBottom: 12,
    };
  }
  return {
    padding: "10px 14px",
    background: "var(--err-bg)",
    border: "1px solid var(--err-border)",
    borderRadius: 6,
    color: "var(--err)",
    fontSize: 13,
    marginBottom: 12,
  };
}

function queryString(values: Record<string, string | undefined>): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) {
    if (value) query.set(key, value);
  }
  const asString = query.toString();
  return asString ? `?${asString}` : "";
}

function parseExportIds(singleId?: string, idsCsv?: string): string[] {
  const all = [singleId ?? "", ...(idsCsv ?? "").split(",")]
    .map((value) => value.trim())
    .filter(Boolean);
  return Array.from(new Set(all)).slice(0, 20);
}

function jobStatusBadge(status: string) {
  const normalized = status.toLowerCase();
  if (normalized === "completed" || normalized === "ready") {
    return (
      <span className="evo-badge evo-badge--ok">
        <span className="evo-badge__dot" />
        concluido
      </span>
    );
  }
  if (normalized === "running" || normalized === "queued") {
    return (
      <span className="evo-badge evo-badge--info">
        <span className="evo-badge__dot" />
        em andamento
      </span>
    );
  }
  return (
    <span className="evo-badge evo-badge--err">
      <span className="evo-badge__dot" />
      erro
    </span>
  );
}

function exportName(job: ExportJob): string {
  const env = typeof job.filters.environment === "string" ? `env:${job.filters.environment}` : "env:any";
  const status = typeof job.filters.status === "string" ? `status:${job.filters.status}` : "status:any";
  const nameContains = typeof job.filters.name_contains === "string" ? `name:${job.filters.name_contains}` : null;
  return [env, status, nameContains].filter(Boolean).join(" | ");
}

function exportSource(job: ExportJob): string {
  const env = typeof job.filters.environment === "string" ? job.filters.environment : "all-env";
  return `traces/${env}`;
}

function percent(value: number, limit: number): number {
  if (!limit || limit <= 0) return 0;
  return Math.max(0, Math.min(100, (value / limit) * 100));
}

function UsageBar({ label, value, limit }: { label: string; value: number; limit: number }) {
  const pct = percent(value, limit);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "var(--text-muted)" }}>
        <span>{label}</span>
        <span className="evo-mono">{formatCount(value)} / {formatCount(limit)}</span>
      </div>
      <div style={{ height: 6, background: "var(--bg-2)", borderRadius: 999, overflow: "hidden" }}>
        <div style={{ width: `${pct}%`, height: "100%", background: pct > 90 ? "var(--warn)" : "var(--accent)" }} />
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

  const basePath = `/o/${org}/p/${project}/exports`;
  const tab = qp.tab ?? "all";
  const knownIds = parseExportIds(qp.export_id, qp.ids);

  let resolvedProject: Awaited<ReturnType<typeof resolveProject>>;
  try {
    resolvedProject = await resolveProject(org, project);
  } catch (error) {
    const message = safeErrorMessage(error, "Falha ao resolver projeto.");
    return (
      <div className="evo-page">
        <div className="evo-page-header">
          <div>
            <h1 className="evo-page-header__title">Exports</h1>
            <p className="evo-page-header__subtitle">Jobs de exportacao para JSONL e auditoria.</p>
          </div>
          <div className="evo-page-header__actions">
            <Link href={basePath} className="evo-btn evo-btn--sm">
              <RefreshCw size={13} />
              Tentar novamente
            </Link>
          </div>
        </div>
        <div style={alertStyle("err")}>Nao foi possivel carregar o projeto. Detalhe: {message}</div>
      </div>
    );
  }

  const [usageResult, subResult, exportRows] = await Promise.all([
    getOrganizationUsage(resolvedProject.org_id)
      .then((usage) => ({ usage, error: null as string | null }))
      .catch((error) => ({ usage: null, error: safeErrorMessage(error, "Falha ao carregar uso.") })),
    getOrganizationSubscription(resolvedProject.org_id)
      .then((subscription) => ({ subscription, error: null as string | null }))
      .catch((error) => ({ subscription: null, error: safeErrorMessage(error, "Falha ao carregar plano.") })),
    Promise.all(
      knownIds.map(async (id): Promise<ExportRow> => {
        try {
          const job = await getExport(id);
          return { id, job, error: null };
        } catch (error) {
          return { id, job: null, error: safeErrorMessage(error, "Falha ao consultar export.") };
        }
      }),
    ),
  ]);

  const runningCount = exportRows.filter((row) => row.job && ["running", "queued"].includes(row.job.status.toLowerCase())).length;
  const completedCount = exportRows.filter((row) => row.job?.status.toLowerCase() === "completed").length;
  const failedCount = exportRows.filter((row) => row.error || (row.job && ["error", "failed"].includes(row.job.status.toLowerCase()))).length;

  const filteredRows = exportRows.filter((row) => {
    const status = row.job?.status.toLowerCase();
    if (tab === "running") return status === "running" || status === "queued";
    if (tab === "completed") return status === "completed";
    if (tab === "failed") return Boolean(row.error) || status === "error" || status === "failed";
    return true;
  });

  const idsValue = knownIds.join(",");
  const tabHref = (nextTab: string) =>
    `${basePath}${queryString({
      tab: nextTab === "all" ? undefined : nextTab,
      ids: idsValue || undefined,
    })}`;

  return (
    <div className="evo-page">
      <div className="evo-page-header">
        <div>
          <h1 className="evo-page-header__title">Exports</h1>
          <p className="evo-page-header__subtitle">
            Exports para JSONL, auditoria e analise offline com dados reais de traces.
          </p>
        </div>
        <div className="evo-page-header__actions">
          <Link href={tabHref(tab)} className="evo-btn evo-btn--sm">
            <RefreshCw size={13} />
            Atualizar
          </Link>
          <Link href="#create-export" className="evo-btn evo-btn--sm evo-btn--primary">
            <Plus size={13} />
            Novo export
          </Link>
        </div>
      </div>

      {qp.created === "1" && <div style={alertStyle("ok")}>Export criado e adicionado na lista de jobs conhecidos.</div>}
      {qp.error && <div style={alertStyle("err")}>{qp.error}</div>}

      <section className="evo-kpi-grid" style={{ marginBottom: 16 }}>
        <div className="evo-metric" style={{ minHeight: 112 }}>
          <div className="evo-metric__label">Jobs conhecidos</div>
          <div className="evo-metric__value">{exportRows.length.toLocaleString("pt-BR")}</div>
          <div className="evo-metric__delta evo-metric__delta--neutral">consultados por ID</div>
        </div>
        <div className="evo-metric" style={{ minHeight: 112 }}>
          <div className="evo-metric__label">Em andamento</div>
          <div className="evo-metric__value">{runningCount.toLocaleString("pt-BR")}</div>
          <div className="evo-metric__delta evo-metric__delta--neutral">running/queued</div>
        </div>
        <div className="evo-metric" style={{ minHeight: 112 }}>
          <div className="evo-metric__label">Concluidos</div>
          <div className="evo-metric__value">{completedCount.toLocaleString("pt-BR")}</div>
          <div className="evo-metric__delta evo-metric__delta--neutral">prontos</div>
        </div>
        <div className="evo-metric" style={{ minHeight: 112 }}>
          <div className="evo-metric__label">Falhas</div>
          <div className="evo-metric__value">{failedCount.toLocaleString("pt-BR")}</div>
          <div className="evo-metric__delta evo-metric__delta--neutral">erro de job ou consulta</div>
        </div>
      </section>

      <nav className="evo-tabs">
        <Link href={tabHref("all")} className={`evo-tab${tab === "all" ? " is-active" : ""}`}>
          Todos
          <span className="evo-tab__count">{exportRows.length}</span>
        </Link>
        <Link href={tabHref("running")} className={`evo-tab${tab === "running" ? " is-active" : ""}`}>
          Em andamento
          <span className="evo-tab__count">{runningCount}</span>
        </Link>
        <Link href={tabHref("completed")} className={`evo-tab${tab === "completed" ? " is-active" : ""}`}>
          Concluidos
          <span className="evo-tab__count">{completedCount}</span>
        </Link>
        <Link href={tabHref("failed")} className={`evo-tab${tab === "failed" ? " is-active" : ""}`}>
          Falhas
          <span className="evo-tab__count">{failedCount}</span>
        </Link>
      </nav>

      <div className="evo-grid-2col">
        <section className="evo-card" style={{ minWidth: 0 }}>
          <div className="evo-card__header">
            <h3 className="evo-card__title">Jobs de export</h3>
            <span className="evo-faint" style={{ fontSize: 11 }}>
              {filteredRows.length} visivel(is)
            </span>
          </div>
          <div className="evo-card__body evo-card__body--flush">
            <div style={{ overflowX: "auto" }}>
              <table className="evo-table">
                <thead>
                  <tr>
                    <th>Job</th>
                    <th>Formato</th>
                    <th>Linhas</th>
                    <th>Fonte</th>
                    <th>Status</th>
                    <th>Criado em</th>
                    <th>Tamanho</th>
                    <th style={{ width: 190 }} />
                  </tr>
                </thead>
                <tbody>
                  {filteredRows.length === 0 ? (
                    <tr>
                      <td className="evo-empty-row" colSpan={8}>Nenhum export para esse filtro.</td>
                    </tr>
                  ) : (
                    filteredRows.map((row) => {
                      if (row.error || !row.job) {
                        return (
                          <tr key={row.id}>
                            <td>
                              <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                                <span className="evo-table__name">{row.id}</span>
                                <span style={{ fontSize: 11, color: "var(--err)" }}>Falha ao consultar job</span>
                              </div>
                            </td>
                            <td className="evo-faint">-</td>
                            <td className="evo-faint">-</td>
                            <td className="evo-faint">-</td>
                            <td>
                              <span className="evo-badge evo-badge--err">
                                <span className="evo-badge__dot" />
                                erro
                              </span>
                            </td>
                            <td className="evo-faint">-</td>
                            <td className="evo-faint">-</td>
                            <td>
                              <Link href={basePath + queryString({ export_id: row.id, ids: idsValue || undefined })} className="evo-btn evo-btn--sm">
                                <RefreshCw size={13} />
                                Retry
                              </Link>
                            </td>
                          </tr>
                        );
                      }

                      const isComplete = row.job.status.toLowerCase() === "completed";
                      const filePath = row.job.file_path ?? "";

                      return (
                        <tr key={row.id}>
                          <td>
                            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                              <span className="evo-table__name">{exportName(row.job)}</span>
                              <span style={{ fontSize: 11, color: "var(--text-faint)", fontFamily: "var(--font-mono)" }}>
                                {row.job.id}
                              </span>
                            </div>
                          </td>
                          <td>
                            <span className="evo-mono evo-muted" style={{ fontSize: 12 }}>{row.job.format}</span>
                          </td>
                          <td className="evo-table__num">{formatCount(row.job.row_count)}</td>
                          <td>
                            <span className="evo-tag">{exportSource(row.job)}</span>
                          </td>
                          <td>{jobStatusBadge(row.job.status)}</td>
                          <td className="evo-muted" style={{ fontSize: 12 }}>{formatDateTime(row.job.created_at)}</td>
                          <td className="evo-mono evo-muted" style={{ fontSize: 12 }}>nao disponivel</td>
                          <td>
                            <div className="evo-row" style={{ justifyContent: "flex-end" }}>
                              {isComplete && filePath ? (
                                <CopyTextButton
                                  text={filePath}
                                  label="Copiar path"
                                  copiedLabel="Path copiado"
                                  className="evo-btn evo-btn--sm"
                                />
                              ) : null}
                              <button
                                type="button"
                                className="evo-btn evo-btn--sm"
                                disabled
                                style={{ opacity: 0.6 }}
                              >
                                <Download size={13} />
                                Download
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {exportRows.length === 0 && (
            <div className="evo-card__body" style={{ borderTop: "1px solid var(--border-subtle)" }}>
              <p style={{ marginTop: 0, marginBottom: 8, color: "var(--text)", fontWeight: 600 }}>
                Exports ajudam em JSONL/CSV, auditoria e pipelines externos.
              </p>
              <p style={{ marginTop: 0, marginBottom: 14, color: "var(--text-muted)", fontSize: 13 }}>
                O contrato atual permite criar export e consultar por ID. Nao existe endpoint de historico completo.
              </p>
              <ol style={{ margin: 0, paddingLeft: 18, color: "var(--text-muted)", fontSize: 13, lineHeight: 1.8 }}>
                <li>Crie um export com filtros reais.</li>
                <li>O job criado entra na lista desta pagina via ID.</li>
                <li>Use o path retornado para operacoes internas autorizadas.</li>
              </ol>
            </div>
          )}
        </section>

        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <section id="create-export" className="evo-card">
            <div className="evo-card__header">
              <h3 className="evo-card__title">Criar export</h3>
              <span className="evo-faint" style={{ fontSize: 11 }}>acao real</span>
            </div>
            <div className="evo-card__body">
              <form action={createExportAction} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                <input type="hidden" name="org" value={org} />
                <input type="hidden" name="project" value={project} />
                <input type="hidden" name="project_id" value={resolvedProject.project_id} />
                <input type="hidden" name="known_export_ids" value={idsValue} />

                <label style={LABEL_STYLE}>
                  <span style={{ color: "var(--text-muted)" }}>Ambiente</span>
                  <select name="environment" defaultValue="" style={INPUT_STYLE}>
                    <option value="">todos</option>
                    <option value="dev">dev</option>
                    <option value="staging">staging</option>
                    <option value="prod">prod</option>
                  </select>
                </label>

                <label style={LABEL_STYLE}>
                  <span style={{ color: "var(--text-muted)" }}>Status</span>
                  <select name="status" defaultValue="" style={INPUT_STYLE}>
                    <option value="">todos</option>
                    <option value="ok">ok</option>
                    <option value="partial">partial</option>
                    <option value="error">error</option>
                  </select>
                </label>

                <label style={LABEL_STYLE}>
                  <span style={{ color: "var(--text-muted)" }}>Nome contem (opcional)</span>
                  <input name="name_contains" placeholder="checkout" style={INPUT_STYLE} />
                </label>

                <button type="submit" className="evo-btn evo-btn--primary" style={{ alignSelf: "flex-start" }}>
                  <Plus size={13} />
                  Gerar export
                </button>
              </form>
            </div>
          </section>

          <section className="evo-card">
            <div className="evo-card__header">
              <h3 className="evo-card__title">Plano e uso</h3>
            </div>
            <div className="evo-card__body" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {subResult.subscription ? (
                <>
                  <div>
                    <div style={{ color: "var(--text)", fontSize: 14, fontWeight: 600 }}>
                      {subResult.subscription.plan.name}
                    </div>
                    <div style={{ color: "var(--text-faint)", fontSize: 12 }}>
                      {subResult.subscription.plan.code}
                    </div>
                  </div>
                  {usageResult.usage ? (
                    <>
                      <div className="evo-mono" style={{ color: "var(--text)", fontSize: 18 }}>
                        {formatCost(usageResult.usage.cost_usd)}
                      </div>
                      <div style={{ color: "var(--text-faint)", fontSize: 12 }}>
                        periodo: {usageResult.usage.period}
                      </div>
                      <UsageBar
                        label="Traces"
                        value={usageResult.usage.traces_ingested}
                        limit={subResult.subscription.plan.monthly_trace_limit}
                      />
                      <UsageBar
                        label="Avaliacoes"
                        value={usageResult.usage.evaluations_run}
                        limit={subResult.subscription.plan.monthly_eval_limit}
                      />
                      <UsageBar
                        label="Exports"
                        value={usageResult.usage.exports_created}
                        limit={subResult.subscription.plan.monthly_export_limit}
                      />
                    </>
                  ) : (
                    <p style={{ margin: 0, color: "var(--warn)", fontSize: 12 }}>
                      Falha ao carregar uso: {usageResult.error}
                    </p>
                  )}
                </>
              ) : (
                <p style={{ margin: 0, color: "var(--warn)", fontSize: 12 }}>
                  Falha ao carregar assinatura: {subResult.error}
                </p>
              )}
            </div>
          </section>

          <section className="evo-card">
            <div className="evo-card__header">
              <h3 className="evo-card__title">Acoes indisponiveis no contrato atual</h3>
            </div>
            <div className="evo-card__body" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <p style={{ margin: 0, color: "var(--text-faint)", fontSize: 12 }}>
                O backend atual nao expone endpoint para listar historico global, cancelar job ou baixar arquivo por URL publica.
              </p>
              <p style={{ margin: 0, color: "var(--text-faint)", fontSize: 12 }}>
                Por isso os botoes de download/retry global ficam limitados ao que o contrato retorna hoje.
              </p>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}


