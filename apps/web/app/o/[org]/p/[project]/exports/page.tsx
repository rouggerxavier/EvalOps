import Link from "next/link";
import { Download, Plus, RefreshCw } from "lucide-react";

import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { createExportAction } from "@/lib/actions";
import {
  getExport,
  getExportDownloadPath,
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
      <span className="badge badge--ok">
        <span className="badge__dot" />
        concluido
      </span>
    );
  }
  if (normalized === "running" || normalized === "queued") {
    return (
      <span className="badge badge--info">
        <span className="badge__dot" />
        em andamento
      </span>
    );
  }
  return (
    <span className="badge badge--err">
      <span className="badge__dot" />
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

function relTime(iso: string): string {
  const diff = Date.now() - Date.parse(iso);
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "agora";
  if (mins < 60) return `${mins}m atrás`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h atrás`;
  return `${Math.floor(hrs / 24)}d atrás`;
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
        <span className="mono">{formatCount(value)} / {formatCount(limit)}</span>
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
      <div className="page">
        <div className="page-header">
          <div>
            <p className="page-header__eyebrow">Dados · Exports</p>
            <h1 className="page-header__title">Exports</h1>
            <p className="page-header__subtitle">Jobs de exportacao para JSONL e auditoria.</p>
          </div>
          <div className="page-header__actions">
            <Link href={basePath} className="btn btn--sm">
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
  const latestActivity = (() => {
    let mostRecent: string | null = null;
    for (const row of exportRows) {
      const value = row.job?.created_at;
      if (!value) continue;
      if (!mostRecent || Date.parse(value) > Date.parse(mostRecent)) {
        mostRecent = value;
      }
    }
    return mostRecent;
  })();

  const filteredRows = exportRows.filter((row) => {
    const status = row.job?.status.toLowerCase();
    if (tab === "running") return status === "running" || status === "queued";
    if (tab === "completed") return status === "completed";
    if (tab === "failed") return Boolean(row.error) || status === "error" || status === "failed";
    return true;
  });

  const idsValue = knownIds.join(",");
  const sanitizedQueryError = qp.error ? safeErrorMessage(qp.error, "Falha ao carregar exports.") : null;
  const currentViewHref = `${basePath}${queryString({
    tab: tab === "all" ? undefined : tab,
    ids: idsValue || undefined,
  })}`;
  const tabHref = (nextTab: string) =>
    `${basePath}${queryString({
      tab: nextTab === "all" ? undefined : nextTab,
      ids: idsValue || undefined,
    })}`;

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <p className="page-header__eyebrow">Dados · Exports</p>
          <h1 className="page-header__title">Exports</h1>
          <p className="page-header__subtitle">
            Exports para JSONL, auditoria e analise offline com dados reais de traces.
          </p>
        </div>
        <div className="page-header__actions">
          <Link href={tabHref(tab)} className="btn btn--sm">
            <RefreshCw size={13} />
            Atualizar
          </Link>
          <Link href="#create-export" className="btn btn--sm btn--primary">
            <Plus size={13} />
            Novo export
          </Link>
        </div>
      </div>

      {qp.created === "1" && <div style={alertStyle("ok")}>Export criado e adicionado na lista de jobs conhecidos.</div>}
      {sanitizedQueryError && <div style={alertStyle("err")}>{sanitizedQueryError}</div>}

      <section className="module-summary" aria-label="Resumo de exports">
        <div className="summary-card">
          <p className="summary-card__label">Jobs conhecidos</p>
          <div className="summary-card__value">{exportRows.length.toLocaleString("pt-BR")}</div>
          <div className="summary-card__hint">consultados por ID</div>
        </div>
        <div className="summary-card">
          <p className="summary-card__label">Em andamento</p>
          <div className="summary-card__value">{runningCount.toLocaleString("pt-BR")}</div>
          <div className="summary-card__hint">running/queued</div>
        </div>
        <div className="summary-card">
          <p className="summary-card__label">Concluídos</p>
          <div className="summary-card__value">{completedCount.toLocaleString("pt-BR")}</div>
          <div className="summary-card__hint">prontos para download</div>
        </div>
        <div className="summary-card">
          <p className="summary-card__label">Última atividade</p>
          <div className="summary-card__value">
            {latestActivity ? relTime(latestActivity) : "—"}
          </div>
          <div className="summary-card__hint">job mais recente consultado</div>
        </div>
      </section>

      <nav className="tabs">
        <Link href={tabHref("all")} className={`tab${tab === "all" ? " is-active" : ""}`}>
          Todos
          <span className="tab__count">{exportRows.length}</span>
        </Link>
        <Link href={tabHref("running")} className={`tab${tab === "running" ? " is-active" : ""}`}>
          Em andamento
          <span className="tab__count">{runningCount}</span>
        </Link>
        <Link href={tabHref("completed")} className={`tab${tab === "completed" ? " is-active" : ""}`}>
          Concluidos
          <span className="tab__count">{completedCount}</span>
        </Link>
        <Link href={tabHref("failed")} className={`tab${tab === "failed" ? " is-active" : ""}`}>
          Falhas
          <span className="tab__count">{failedCount}</span>
        </Link>
      </nav>

      <div className="grid-detail">
        <section className="card" style={{ minWidth: 0 }}>
          <div className="card__header">
            <h3 className="card__title">Jobs de export</h3>
            <span className="t__faint" style={{ fontSize: 11 }}>
              {filteredRows.length} visivel(is)
            </span>
          </div>
          <div className="card__body card__body--flush">
            <div style={{ overflowX: "auto" }}>
              <table className="t">
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
                      <td className="empty-row" colSpan={8}>Nenhum export para esse filtro.</td>
                    </tr>
                  ) : (
                    filteredRows.map((row) => {
                      if (row.error || !row.job) {
                        return (
                          <tr key={row.id}>
                            <td>
                              <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                                <span className="t__name">{row.id}</span>
                                <span style={{ fontSize: 11, color: "var(--err)" }}>Falha ao consultar job</span>
                              </div>
                            </td>
                            <td className="t__faint">-</td>
                            <td className="t__faint">-</td>
                            <td className="t__faint">-</td>
                            <td>
                              <span className="badge badge--err">
                                <span className="badge__dot" />
                                erro
                              </span>
                            </td>
                            <td className="t__faint">-</td>
                            <td className="t__faint">-</td>
                            <td>
                              <Link href={basePath + queryString({ export_id: row.id, ids: idsValue || undefined })} className="btn btn--sm">
                                <RefreshCw size={13} />
                                Retry
                              </Link>
                            </td>
                          </tr>
                        );
                      }

                      const status = row.job.status.toLowerCase();
                      const isComplete = status === "completed" || status === "ready";
                      const isRunning = status === "running" || status === "queued";
                      const isFailed = status === "failed" || status === "error";
                      const isDownloadReady = isComplete && Boolean(row.job.file_path);

                      return (
                        <tr key={row.id}>
                          <td>
                            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                              <span className="t__name">{exportName(row.job)}</span>
                              <span style={{ fontSize: 11, color: "var(--text-faint)", fontFamily: "var(--font-mono)" }}>
                                {row.job.id}
                              </span>
                            </div>
                          </td>
                          <td>
                            <span className="mono t__muted" style={{ fontSize: 12 }}>{row.job.format}</span>
                          </td>
                          <td className="t__num">{formatCount(row.job.row_count)}</td>
                          <td>
                            <span className="tag">{exportSource(row.job)}</span>
                          </td>
                          <td>{jobStatusBadge(row.job.status)}</td>
                          <td className="t__muted" style={{ fontSize: 12 }}>{formatDateTime(row.job.created_at)}</td>
                          <td className="mono t__muted" style={{ fontSize: 12 }}>nao disponivel</td>
                          <td>
                            <div className="row" style={{ justifyContent: "flex-end" }}>
                              {isDownloadReady ? (
                                <Link
                                  href={getExportDownloadPath(row.job.id, currentViewHref)}
                                  className="btn btn--sm"
                                  download
                                >
                                  <Download size={13} />
                                  Download
                                </Link>
                              ) : (
                                <button
                                  type="button"
                                  className="btn btn--sm"
                                  disabled
                                  style={{ opacity: 0.6 }}
                                  title={
                                    isRunning
                                      ? "Export ainda em andamento"
                                      : isFailed
                                      ? "Export com falha"
                                      : isComplete
                                      ? "Arquivo indisponível"
                                      : "Export indisponível"
                                  }
                                >
                                  <Download size={13} />
                                  {isRunning ? "Processando" : isFailed ? "Falhou" : "Download"}
                                </button>
                              )}
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
            <div className="card__body" style={{ borderTop: "1px solid var(--border-subtle)" }}>
              <p style={{ marginTop: 0, marginBottom: 8, color: "var(--text)", fontWeight: 600 }}>
                Exports ajudam em JSONL/CSV, auditoria e pipelines externos.
              </p>
              <p style={{ marginTop: 0, marginBottom: 14, color: "var(--text-muted)", fontSize: 13 }}>
                O contrato atual permite criar export e consultar por ID. Nao existe endpoint de historico completo.
              </p>
              <ol style={{ margin: 0, paddingLeft: 18, color: "var(--text-muted)", fontSize: 13, lineHeight: 1.8 }}>
                <li>Crie um export com filtros reais.</li>
                <li>O job criado entra na lista desta pagina via ID.</li>
                <li>Quando o status ficar concluido, use o botao Download para baixar o JSONL.</li>
              </ol>
            </div>
          )}
        </section>

        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <section id="create-export" className="card">
            <div className="card__header">
              <h3 className="card__title">Criar export</h3>
              <span className="t__faint" style={{ fontSize: 11 }}>acao real</span>
            </div>
            <div className="card__body">
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

                <button type="submit" className="btn btn--primary" style={{ alignSelf: "flex-start" }}>
                  <Plus size={13} />
                  Gerar export
                </button>
              </form>
            </div>
          </section>

          <section className="card">
            <div className="card__header">
              <h3 className="card__title">Plano e uso</h3>
            </div>
            <div className="card__body" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
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
                      <div className="mono" style={{ color: "var(--text)", fontSize: 18 }}>
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
                      <UsageBar
                        label="Spans"
                        value={usageResult.usage.spans_ingested}
                        limit={subResult.subscription.plan.monthly_span_limit}
                      />
                      <UsageBar
                        label="Tokens"
                        value={usageResult.usage.tokens_ingested}
                        limit={subResult.subscription.plan.monthly_token_limit}
                      />
                      <div
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "baseline",
                          borderTop: "1px solid var(--border-subtle)",
                          paddingTop: 10,
                        }}
                      >
                        <span style={{ color: "var(--text-muted)", fontSize: 12 }}>Budget mensal de judge</span>
                        <span className="mono" style={{ color: "var(--text)", fontSize: 13 }}>
                          {formatCost(subResult.subscription.plan.monthly_judge_budget_usd)}
                        </span>
                      </div>
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

          <section className="card">
            <div className="card__header">
              <h3 className="card__title">Contrato atual</h3>
            </div>
            <div className="card__body" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <p style={{ margin: 0, color: "var(--text-faint)", fontSize: 12 }}>
                O backend atual nao expoe endpoint para listar historico global nem cancelar jobs.
              </p>
              <p style={{ margin: 0, color: "var(--text-faint)", fontSize: 12 }}>
                O download de exports concluidos usa o endpoint autenticado do proprio contrato.
              </p>
            </div>
          </section>
        </div>
      </div>

      <section className="card" style={{ marginTop: 12 }}>
        <div className="card__header">
          <div>
            <h3 className="card__title">Endpoints ativos</h3>
            <div className="card__subtitle">Rotas reais do backend que servem este módulo.</div>
          </div>
        </div>
        <div className="card__body">
          <div className="endpoint-list" aria-label="Endpoints do módulo Exports">
            <div className="endpoint-row">
              <span className="endpoint-snippet__method method-POST">POST</span>
              <span className="endpoint-row__path" title="/v1/exports">
                /exports
              </span>
              <span className="endpoint-row__note">ativo · cria job</span>
            </div>
            <div className="endpoint-row">
              <span className="endpoint-snippet__method method-GET">GET</span>
              <span className="endpoint-row__path" title="/v1/exports/{export_id}">
                /exports/{"{export_id}"}
              </span>
              <span className="endpoint-row__note">ativo · status do job</span>
            </div>
            <div className="endpoint-row">
              <span className="endpoint-snippet__method method-GET">GET</span>
              <span className="endpoint-row__path" title="/api/exports/{export_id}/download (Next proxy autenticado)">
                /api/exports/{"{export_id}"}/download
              </span>
              <span className="endpoint-row__note">ativo · proxy autenticado</span>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
