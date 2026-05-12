import Link from "next/link";
import { AlertCircle, ChevronRight, Clock, Download, Flag, RefreshCw } from "lucide-react";

import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { TracesFilterBar } from "@/components/TracesFilterBar";
import { getTraces, hasAuthToken, resolveProject } from "@/lib/api";
import { formatCost, formatDateTime, formatLatency } from "@/lib/format";

type Props = {
  params: Promise<{ org: string; project: string }>;
  searchParams: Promise<{ status?: string; environment?: string; name?: string; tab?: string }>;
};

function StatusBadge({ status }: { status: string }) {
  const cls =
    status === "ok" ? "evo-badge--ok" : status === "error" ? "evo-badge--err" : "evo-badge--warn";
  const label = status === "ok" ? "OK" : status === "error" ? "Erro" : "Partial";
  return (
    <span className={`evo-badge ${cls}`}>
      <span className="evo-badge__dot" />
      {label}
    </span>
  );
}

export default async function TracesListPage({ params, searchParams }: Props) {
  const { org, project } = await params;
  const qp = await searchParams;
  const tab = qp.tab ?? "all";

  if (!(await hasAuthToken())) return <AuthRequiredPanel layout="main" />;

  const resolved = await resolveProject(org, project);

  // Fetch all traces (with status filter if on a specific tab)
  const statusFilter = tab === "errors" ? "error" : qp.status;
  const traces = await getTraces({
    projectId: resolved.project_id,
    status: statusFilter,
    environment: qp.environment,
    name: qp.name,
    limit: 50,
  });

  const rows = traces.data;
  const slowRows = rows.filter((t) => t.duration_ms > 2000);
  const errorRows = rows.filter((t) => t.status === "error");

  const tabBase = `/o/${org}/p/${project}/traces`;
  const tabHref = (t: string) =>
    t === "all" ? tabBase : `${tabBase}?tab=${t}`;

  return (
    <div className="evo-page">
      <div className="evo-page-header">
        <div>
          <h1 className="evo-page-header__title">Traces</h1>
          <p className="evo-page-header__subtitle">
            {rows.length.toLocaleString("pt-BR")} no intervalo selecionado
          </p>
        </div>
        <div className="evo-row">
          <button type="button" className="evo-btn evo-btn--sm">
            <Download size={13} /> Exportar JSONL
          </button>
          <button type="button" className="evo-btn evo-btn--sm">
            <RefreshCw size={13} />
          </button>
        </div>
      </div>

      {/* Tabs */}
      <nav className="evo-tabs">
        <Link href={tabHref("all")} className={`evo-tab${tab === "all" ? " is-active" : ""}`}>
          Todos
          <span className="evo-tab__count">{rows.length.toLocaleString("pt-BR")}</span>
        </Link>
        <Link href={tabHref("errors")} className={`evo-tab${tab === "errors" ? " is-active" : ""}`}>
          <AlertCircle size={12} /> Erros
          <span className="evo-tab__count">{errorRows.length}</span>
        </Link>
        <Link href={tabHref("flagged")} className={`evo-tab${tab === "flagged" ? " is-active" : ""}`}>
          <Flag size={12} /> Flagged
          <span className="evo-tab__count">0</span>
        </Link>
        <Link href={tabHref("slow")} className={`evo-tab${tab === "slow" ? " is-active" : ""}`}>
          <Clock size={12} /> Lentos
          <span className="evo-tab__count">{slowRows.length}</span>
        </Link>
      </nav>

      <TracesFilterBar
        initialName={qp.name}
        initialStatus={qp.status}
        initialEnv={qp.environment}
        count={rows.length}
        total={rows.length}
      />

      {rows.length === 0 ? (
        <div className="evo-card" style={{ padding: "48px 24px", textAlign: "center" }}>
          <p style={{ color: "var(--text-muted)", marginBottom: 8, fontWeight: 600 }}>
            Nenhum trace encontrado
          </p>
          <p style={{ color: "var(--text-faint)", fontSize: 13 }}>
            Conecte o SDK Python ou ajuste os filtros para ver traces neste projeto.
          </p>
          <pre
            style={{
              marginTop: 24,
              background: "var(--bg-2)",
              border: "1px solid var(--border-subtle)",
              borderRadius: 8,
              padding: "12px 16px",
              fontSize: 12,
              textAlign: "left",
              display: "inline-block",
              color: "var(--text-dim)",
              fontFamily: "var(--font-mono)",
            }}
          >
            {`import evalops\nevalops.init(api_key="evk_prod_...", project="${project}", environment="prod")\n\n@evalops.trace("chat.answer")\ndef answer(msg: str): ...`}
          </pre>
        </div>
      ) : (
        <>
          <div className="evo-table-wrap">
            <table className="evo-table">
              <thead>
                <tr>
                  <th style={{ width: 32 }}>
                    <input type="checkbox" style={{ accentColor: "var(--accent)" }} />
                  </th>
                  <th className="evo-table__sortable">Nome</th>
                  <th>Trace ID</th>
                  <th>Status</th>
                  <th>Env</th>
                  <th>Modelo</th>
                  <th className="evo-table__sortable">Duração</th>
                  <th className="evo-table__sortable">Tokens</th>
                  <th className="evo-table__sortable">Custo</th>
                  <th>Score</th>
                  <th className="evo-table__sortable">Quando</th>
                  <th style={{ width: 32 }} />
                </tr>
              </thead>
              <tbody>
                {rows.map((trace) => (
                  <tr key={trace.id} style={{ cursor: "pointer" }}>
                    <td>
                      <input type="checkbox" style={{ accentColor: "var(--accent)" }} />
                    </td>
                    <td>
                      <Link
                        href={`/o/${org}/p/${project}/traces/${trace.id}`}
                        style={{ textDecoration: "none", display: "flex", flexDirection: "column", gap: 2 }}
                      >
                        <span className="evo-table__name">{trace.name}</span>
                        {trace.service && (
                          <span style={{ fontSize: 11, color: "var(--text-faint)", fontFamily: "var(--font-mono)" }}>
                            {trace.service}
                          </span>
                        )}
                      </Link>
                    </td>
                    <td>
                      <span className="evo-copyable">
                        <span title={trace.id}>{trace.id.slice(0, 14)}…</span>
                      </span>
                    </td>
                    <td>
                      <StatusBadge status={trace.status} />
                    </td>
                    <td>
                      <span className="evo-tag">{trace.environment}</span>
                    </td>
                    <td className="evo-mono evo-muted" style={{ fontSize: 12 }}>—</td>
                    <td className="evo-table__num">
                      <span
                        style={{
                          color:
                            trace.duration_ms > 4000
                              ? "var(--err)"
                              : trace.duration_ms > 2000
                              ? "var(--warn)"
                              : "var(--text-dim)",
                        }}
                      >
                        {formatLatency(trace.duration_ms)}
                      </span>
                    </td>
                    <td className="evo-table__num evo-muted">
                      {trace.total_tokens_in.toLocaleString("pt-BR")}
                      <span className="evo-faint">/{trace.total_tokens_out.toLocaleString("pt-BR")}</span>
                    </td>
                    <td className="evo-table__num">{formatCost(trace.total_cost_usd)}</td>
                    <td>
                      <span className="evo-faint">—</span>
                    </td>
                    <td className="evo-muted" style={{ fontSize: 12 }}>
                      {formatDateTime(trace.created_at)}
                    </td>
                    <td>
                      <Link href={`/o/${org}/p/${project}/traces/${trace.id}`}>
                        <ChevronRight size={14} style={{ color: "var(--text-faint)" }} />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginTop: 16,
              fontSize: 12,
              color: "var(--text-muted)",
            }}
          >
            <span>
              Mostrando {rows.length.toLocaleString("pt-BR")} trace
              {rows.length !== 1 ? "s" : ""}
            </span>
            <div className="evo-row">
              <button type="button" className="evo-btn evo-btn--sm" disabled>
                ‹
              </button>
              <span className="evo-mono" style={{ fontSize: 12 }}>1</span>
              <button
                type="button"
                className="evo-btn evo-btn--sm"
                disabled={!traces.next_cursor}
              >
                ›
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
