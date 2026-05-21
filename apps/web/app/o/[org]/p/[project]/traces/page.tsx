import Link from "next/link";
import { AlertCircle, Clock, Download, Flag, Layers, Search } from "lucide-react";

import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { getTraces, hasAuthToken, resolveProject } from "@/lib/api";

import { TracesAutoRefresh } from "./traces-auto-refresh";
import { TracesEmpty, TracesTable } from "./traces-table";

type Tab = "all" | "errors" | "partial" | "slow" | "rag";

type Props = {
  params: Promise<{ org: string; project: string }>;
  searchParams: Promise<{
    status?: string;
    environment?: string;
    name?: string;
    tab?: string;
    cursor?: string;
  }>;
};

function parseTab(value: string | undefined): Tab {
  if (value === "errors" || value === "partial" || value === "slow" || value === "rag") return value;
  return "all";
}

export default async function TracesListPage({ params, searchParams }: Props) {
  const { org, project } = await params;
  const qp = await searchParams;
  const tab = parseTab(qp.tab);

  if (!(await hasAuthToken())) return <AuthRequiredPanel layout="main" />;

  const resolved = await resolveProject(org, project);

  const tabStatus = tab === "errors" ? "error" : tab === "partial" ? "partial" : qp.status;
  const traces = await getTraces({
    projectId: resolved.project_id,
    status: tabStatus,
    environment: qp.environment,
    name: tab !== "rag" ? qp.name : undefined,
    limit: 50,
    cursor: qp.cursor,
    duration_gt: tab === "slow" ? 2000 : undefined,
    rag: tab === "rag" ? true : undefined,
  });

  const rows = traces.data;
  const displayRows = rows;

  const counts = {
    all: tab === "all" ? rows.length : undefined,
    errors: tab === "errors" ? rows.length : undefined,
    partial: tab === "partial" ? rows.length : undefined,
    slow: tab === "slow" ? rows.length : undefined,
    rag: tab === "rag" ? rows.length : undefined,
  };

  const tabBase = `/o/${org}/p/${project}/traces`;
  const baseParams = new URLSearchParams();
  if (qp.environment) baseParams.set("environment", qp.environment);
  if (qp.name && tab !== "rag") baseParams.set("name", qp.name);
  if (qp.status && tab !== "errors" && tab !== "partial") baseParams.set("status", qp.status);

  const tabHref = (t: Tab) => {
    const p = new URLSearchParams(baseParams);
    if (t !== "all") p.set("tab", t);
    const s = p.toString();
    return s ? `${tabBase}?${s}` : tabBase;
  };

  const nextPageHref = traces.next_cursor
    ? (() => {
        const p = new URLSearchParams(baseParams);
        if (tab !== "all") p.set("tab", tab);
        p.set("cursor", traces.next_cursor);
        return `${tabBase}?${p.toString()}`;
      })()
    : null;

  const exportsHref = `/o/${org}/p/${project}/exports`;
  const hasCursor = Boolean(qp.cursor);
  const autoRefreshEnabled = !hasCursor && rows.length > 0;
  const autoRefreshDisabledReason = hasCursor ? "Pausado em página paginada" : undefined;

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <div className="page-header__eyebrow">Observabilidade</div>
          <h1 className="page-header__title">Traces</h1>
          <div className="page-header__subtitle">
            {rows.length.toLocaleString("pt-BR")} trace{rows.length === 1 ? "" : "s"} na página atual · auto-refresh 30s
          </div>
        </div>
        <div className="page-header__actions">
          {autoRefreshEnabled ? (
            <span className="env-chip" title="Auto-refresh ativo">
              <span className="env-chip__dot" />
              ao vivo
            </span>
          ) : null}
          <Link href={exportsHref} className="btn btn--sm">
            <Download size={12} /> Exportar JSONL
          </Link>
          <TracesAutoRefresh
            enabledByDefault={autoRefreshEnabled}
            intervalMs={30_000}
            disabledReason={autoRefreshDisabledReason}
          />
        </div>
      </header>

      <nav className="tabs" aria-label="Segmentos de traces">
        <Link href={tabHref("all")} className={`tab${tab === "all" ? " is-active" : ""}`}>
          Todos
          <span className="tab__count">{counts.all}</span>
        </Link>
        <Link href={tabHref("errors")} className={`tab${tab === "errors" ? " is-active" : ""}`}>
          <AlertCircle size={11} /> Erros
          <span className="tab__count">{counts.errors}</span>
        </Link>
        <Link href={tabHref("partial")} className={`tab${tab === "partial" ? " is-active" : ""}`}>
          <Flag size={11} /> Parciais
          <span className="tab__count">{counts.partial}</span>
        </Link>
        <Link href={tabHref("slow")} className={`tab${tab === "slow" ? " is-active" : ""}`}>
          <Clock size={11} /> Lentos
          <span className="tab__count">{counts.slow}</span>
        </Link>
        <Link
          href={tabHref("rag")}
          className={`tab${tab === "rag" ? " is-active" : ""}`}
          data-testid="trace-list-rag-tab"
        >
          <Layers size={11} /> RAG
          <span className="tab__count">{counts.rag}</span>
        </Link>
      </nav>

      <form method="get" className="filters" action={tabBase}>
        {tab !== "all" ? <input type="hidden" name="tab" value={tab} /> : null}
        <label className="filter-group">
          <Search size={12} />
          <input
            className="filter-input"
            name="name"
            defaultValue={qp.name ?? ""}
            placeholder="buscar por nome (ex: refund, chat.answer)"
          />
        </label>
        <select className="filter-select" name="status" defaultValue={qp.status ?? ""}>
          <option value="">qualquer status</option>
          <option value="ok">ok</option>
          <option value="partial">parcial</option>
          <option value="error">erro</option>
        </select>
        <select className="filter-select" name="environment" defaultValue={qp.environment ?? ""}>
          <option value="">qualquer env</option>
          <option value="prod">prod</option>
          <option value="staging">staging</option>
          <option value="dev">dev</option>
        </select>
        <button type="submit" className="btn btn--sm">
          Aplicar
        </button>
        <span className="spacer" />
        <span className="faint mono" style={{ fontSize: 11 }}>
          {displayRows.length} de {rows.length}
        </span>
      </form>

      {displayRows.length === 0 ? (
        <TracesEmpty project={project} />
      ) : (
        <TracesTable org={org} project={project} rows={displayRows} />
      )}

      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          marginTop: 12,
          fontSize: 11.5,
          color: "var(--fg-3)",
        }}
      >
        <span>
          Mostrando {displayRows.length.toLocaleString("pt-BR")} trace{displayRows.length === 1 ? "" : "s"}
          {hasCursor ? " (próxima página)" : ""}
        </span>
        <div className="row" style={{ gap: 6 }}>
          <button type="button" className="btn btn--sm btn--ghost" disabled>
            ‹
          </button>
          {nextPageHref ? (
            <Link href={nextPageHref} className="btn btn--sm btn--ghost">
              ›
            </Link>
          ) : (
            <button type="button" className="btn btn--sm btn--ghost" disabled>
              ›
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
