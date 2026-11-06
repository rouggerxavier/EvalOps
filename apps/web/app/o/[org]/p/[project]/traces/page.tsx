import Link from "next/link";
import { AlertCircle, Clock, Download, Flag, Layers, Search, X } from "lucide-react";

import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { getActiveEnvironment } from "@/lib/active-env";
import { getTraces, hasAuthToken, resolveProject } from "@/lib/api";

import { TracesAutoRefresh } from "./traces-auto-refresh";
import { TracesEmpty, TracesTable } from "./traces-table";

type Tab = "all" | "errors" | "partial" | "slow" | "rag" | "flagged";
type SlowKind = "trace" | "llm" | "retrieval";

type Props = {
  params: Promise<{ org: string; project: string }>;
  searchParams: Promise<{
    status?: string;
    environment?: string;
    name?: string;
    tab?: string;
    cursor?: string;
    slow_kind?: string;
    q?: string;
    conversation_id?: string;
    since?: string;
    until?: string;
    tag?: string;
    user_ref?: string;
    model?: string;
    failed?: string;
    score_lt?: string;
  }>;
};

// Filters kept across tabs, pagination and refresh; invalid values are dropped so the API never answers 422.
const FILTER_KEYS = ["q", "conversation_id", "since", "until", "tag", "user_ref", "model", "failed", "score_lt"] as const;
type FilterKey = (typeof FILTER_KEYS)[number];

function validFilters(qp: Partial<Record<FilterKey, string>>): Partial<Record<FilterKey, string>> {
  const out: Partial<Record<FilterKey, string>> = {};
  for (const key of FILTER_KEYS) {
    const value = qp[key]?.trim();
    if (!value) continue;
    if ((key === "since" || key === "until") && !/^\d{4}-\d{2}-\d{2}$/.test(value)) continue;
    if (key === "tag" && !/^[^:]+:.+$/.test(value)) continue;
    if (key === "failed" && value !== "true") continue;
    if (key === "score_lt" && !(Number(value) >= 0 && Number(value) <= 1)) continue;
    out[key] = value;
  }
  return out;
}

function parseTab(value: string | undefined): Tab {
  if (value === "errors" || value === "partial" || value === "slow" || value === "rag" || value === "flagged") return value;
  return "all";
}

function parseSlowKind(value: string | undefined): SlowKind {
  if (value === "llm" || value === "retrieval") return value;
  return "trace";
}

export default async function TracesListPage({ params, searchParams }: Props) {
  const { org, project } = await params;
  const qp = await searchParams;
  const tab = parseTab(qp.tab);

  if (!(await hasAuthToken())) return <AuthRequiredPanel layout="main" />;

  const resolved = await resolveProject(org, project);

  const tabStatus = tab === "errors" ? "error" : tab === "partial" ? "partial" : qp.status;
  const slowKind: SlowKind = tab === "slow" ? parseSlowKind(qp.slow_kind) : "trace";
  const environment = await getActiveEnvironment(qp.environment);
  const filters = validFilters(qp);
  const traces = await getTraces({
    projectId: resolved.project_id,
    status: tabStatus,
    environment,
    name: tab !== "rag" ? qp.name : undefined,
    limit: 50,
    cursor: qp.cursor,
    duration_gt: tab === "slow" ? 2000 : undefined,
    slow_kind: tab === "slow" ? slowKind : undefined,
    rag: tab === "rag" ? true : undefined,
    flagged: tab === "flagged" ? true : undefined,
    q: filters.q,
    conversation_id: filters.conversation_id,
    // shortcut: dates are whole days in UTC, not the viewer's timezone; upgrade when the UI knows the user's timezone
    since: filters.since ? `${filters.since}T00:00:00` : undefined,
    until: filters.until ? `${filters.until}T23:59:59.999` : undefined,
    tag: filters.tag,
    user_ref: filters.user_ref,
    model: filters.model,
    failed: filters.failed ? true : undefined,
    score_lt: filters.score_lt ? Number(filters.score_lt) : undefined,
  });

  const rows = traces.data;
  const displayRows = rows;

  const activeCount = rows.length;

  const tabBase = `/o/${org}/p/${project}/traces`;
  const baseParams = new URLSearchParams();
  // Reflect the *resolved* environment (cookie fallback included) so paginated
  // and refresh links keep the same filter the user is actually seeing.
  if (environment) baseParams.set("environment", environment);
  else if (qp.environment === "") baseParams.set("environment", "");
  if (qp.name && tab !== "rag") baseParams.set("name", qp.name);
  if (qp.status && tab !== "errors" && tab !== "partial") baseParams.set("status", qp.status);
  // Persist slow_kind across pagination, filter submit and refresh links so a
  // user that picked "LLM call" / "Retrieval" doesn't silently fall back to
  // "Trace inteiro" after the next click.
  if (tab === "slow" && slowKind !== "trace") baseParams.set("slow_kind", slowKind);
  for (const [key, value] of Object.entries(filters)) baseParams.set(key, value);

  const withoutFilterHref = (key: FilterKey) => {
    const p = new URLSearchParams(baseParams);
    p.delete(key);
    if (tab !== "all") p.set("tab", tab);
    const s = p.toString();
    return s ? `${tabBase}?${s}` : tabBase;
  };

  const tabHref = (t: Tab) => {
    const p = new URLSearchParams(baseParams);
    if (t !== "all") p.set("tab", t);
    const s = p.toString();
    return s ? `${tabBase}?${s}` : tabBase;
  };

  const slowKindHref = (kind: SlowKind) => {
    const p = new URLSearchParams(baseParams);
    p.set("tab", "slow");
    if (kind !== "trace") p.set("slow_kind", kind);
    return `${tabBase}?${p.toString()}`;
  };

  const nextPageHref = traces.next_cursor
    ? (() => {
        const p = new URLSearchParams(baseParams);
        if (tab !== "all") p.set("tab", tab);
        p.set("cursor", traces.next_cursor);
        return `${tabBase}?${p.toString()}`;
      })()
    : null;

  const firstPageHref = qp.cursor
    ? (() => {
        const p = new URLSearchParams(baseParams);
        if (tab !== "all") p.set("tab", tab);
        const s = p.toString();
        return s ? `${tabBase}?${s}` : tabBase;
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
          {tab === "all" ? <span className="tab__count">{activeCount}</span> : null}
        </Link>
        <Link href={tabHref("errors")} className={`tab${tab === "errors" ? " is-active" : ""}`}>
          <AlertCircle size={11} /> Erros
          {tab === "errors" ? <span className="tab__count">{activeCount}</span> : null}
        </Link>
        <Link href={tabHref("partial")} className={`tab${tab === "partial" ? " is-active" : ""}`}>
          <Flag size={11} /> Parciais
          {tab === "partial" ? <span className="tab__count">{activeCount}</span> : null}
        </Link>
        <Link href={tabHref("slow")} className={`tab${tab === "slow" ? " is-active" : ""}`}>
          <Clock size={11} /> Lentos
          {tab === "slow" ? <span className="tab__count">{activeCount}</span> : null}
        </Link>
        <Link
          href={tabHref("rag")}
          className={`tab${tab === "rag" ? " is-active" : ""}`}
          data-testid="trace-list-rag-tab"
        >
          <Layers size={11} /> RAG
          {tab === "rag" ? <span className="tab__count">{activeCount}</span> : null}
        </Link>
        <Link href={tabHref("flagged")} className={`tab${tab === "flagged" ? " is-active" : ""}`}>
          <Flag size={11} /> Marcados
          {tab === "flagged" ? <span className="tab__count">{activeCount}</span> : null}
        </Link>
      </nav>

      {tab === "slow" ? (
        <nav
          className="tabs tabs--sub"
          aria-label="Origem da lentidão"
          data-testid="slow-kind-tabs"
          style={{ marginTop: 4, fontSize: 12 }}
        >
          <Link
            href={slowKindHref("trace")}
            className={`tab${slowKind === "trace" ? " is-active" : ""}`}
          >
            Trace inteiro
          </Link>
          <Link
            href={slowKindHref("llm")}
            className={`tab${slowKind === "llm" ? " is-active" : ""}`}
          >
            LLM call
          </Link>
          <Link
            href={slowKindHref("retrieval")}
            className={`tab${slowKind === "retrieval" ? " is-active" : ""}`}
          >
            Retrieval
          </Link>
        </nav>
      ) : null}

      <form method="get" className="filters" action={tabBase}>
        {tab !== "all" ? <input type="hidden" name="tab" value={tab} /> : null}
        {tab === "slow" && slowKind !== "trace" ? (
          <input type="hidden" name="slow_kind" value={slowKind} />
        ) : null}
        {filters.q ? <input type="hidden" name="q" value={filters.q} /> : null}
        {filters.conversation_id ? <input type="hidden" name="conversation_id" value={filters.conversation_id} /> : null}
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
        <select className="filter-select" name="environment" defaultValue={environment ?? ""}>
          <option value="">qualquer env</option>
          <option value="prod">prod</option>
          <option value="staging">staging</option>
          <option value="dev">dev</option>
        </select>
        <label className="row faint" style={{ gap: 4, fontSize: 11.5 }}>
          de
          <input className="filter-input" type="date" name="since" defaultValue={filters.since ?? ""} style={{ minWidth: 0, padding: "0 6px" }} />
        </label>
        <label className="row faint" style={{ gap: 4, fontSize: 11.5 }}>
          até
          <input className="filter-input" type="date" name="until" defaultValue={filters.until ?? ""} style={{ minWidth: 0, padding: "0 6px" }} />
        </label>
        <input
          className="filter-input"
          name="tag"
          defaultValue={filters.tag ?? ""}
          placeholder="tag (ex: canal:whatsapp)"
          aria-label="Tag no formato chave:valor"
          style={{ minWidth: 150, padding: "0 10px" }}
        />
        <input
          className="filter-input"
          name="user_ref"
          defaultValue={filters.user_ref ?? ""}
          placeholder="usuário"
          aria-label="Usuário"
          style={{ minWidth: 110, padding: "0 10px" }}
        />
        <input
          className="filter-input"
          name="model"
          defaultValue={filters.model ?? ""}
          placeholder="modelo (ex: gpt-4o-mini)"
          aria-label="Modelo"
          style={{ minWidth: 150, padding: "0 10px" }}
        />
        <input
          className="filter-input"
          type="number"
          name="score_lt"
          min={0}
          max={1}
          step={0.05}
          defaultValue={filters.score_lt ?? ""}
          placeholder="nota abaixo de"
          aria-label="Nota abaixo de (0 a 1)"
          style={{ minWidth: 0, width: 120, padding: "0 10px" }}
        />
        <label className="row faint" style={{ gap: 4, fontSize: 11.5 }}>
          <input type="checkbox" name="failed" value="true" defaultChecked={Boolean(filters.failed)} style={{ accentColor: "var(--primary-400)" }} />
          só reprovados
        </label>
        <button type="submit" className="btn btn--sm">
          Aplicar
        </button>
        <span className="spacer" />
        <span className="faint mono" style={{ fontSize: 11 }}>
          {displayRows.length} de {rows.length}
        </span>
      </form>

      {filters.q || filters.conversation_id ? (
        <div className="row" style={{ gap: 6, marginBottom: 8 }}>
          {filters.conversation_id ? (
            <span className="tag" data-testid="conversation-filter-chip">
              conversa: {filters.conversation_id}
              <Link href={withoutFilterHref("conversation_id")} aria-label="Remover filtro de conversa" style={{ marginLeft: 6, color: "inherit" }}>
                <X size={11} />
              </Link>
            </span>
          ) : null}
          {filters.q ? (
            <span className="tag">
              busca: {filters.q}
              <Link href={withoutFilterHref("q")} aria-label="Remover busca" style={{ marginLeft: 6, color: "inherit" }}>
                <X size={11} />
              </Link>
            </span>
          ) : null}
        </div>
      ) : null}

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
          {firstPageHref ? (
            <Link href={firstPageHref} className="btn btn--sm btn--ghost" title="Voltar à primeira página">
              ‹
            </Link>
          ) : (
            <button type="button" className="btn btn--sm btn--ghost" disabled>
              ‹
            </button>
          )}
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
