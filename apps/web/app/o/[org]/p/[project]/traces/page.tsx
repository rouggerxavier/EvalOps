import Link from "next/link";
import { Clock, Download, GitCompareArrows, Layers, Search, X } from "lucide-react";

import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { getActiveEnvironment } from "@/lib/active-env";
import { getTraces, hasAuthToken, resolveProject } from "@/lib/api";

import { TracesAutoRefresh } from "./traces-auto-refresh";
import { TracesEmpty, TracesTable } from "./traces-table";
import type { EvaluationVerdict } from "./trace-status";

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
    verdict?: string;
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

function isRealDate(value: string): boolean {
  const date = new Date(`${value}T00:00:00Z`);
  return /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(date.getTime()) && date.toISOString().startsWith(value);
}

function validFilters(qp: Partial<Record<FilterKey, string>>): Partial<Record<FilterKey, string>> {
  const out: Partial<Record<FilterKey, string>> = {};
  for (const key of FILTER_KEYS) {
    const value = qp[key]?.trim();
    if (!value) continue;
    // The round trip rejects impossible dates like 2026-02-30, which the API answers with 422.
    if ((key === "since" || key === "until") && !isRealDate(value)) continue;
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

  const tabStatus = tab === "errors" ? "error,partial" : tab === "partial" ? "partial" : qp.status;
  const slowKind: SlowKind = tab === "slow" ? parseSlowKind(qp.slow_kind) : "trace";
  const environment = await getActiveEnvironment(qp.environment);
  const filters = validFilters(qp);
  const verdictFilter = ["approved", "partial", "rejected", "unknown"].includes(qp.verdict ?? "")
    ? qp.verdict as EvaluationVerdict
    : undefined;
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
    verdict: verdictFilter,
  });

  const rows = traces.data;
  const verdicts = Object.fromEntries(rows.map((trace) => [
    trace.id,
    trace.last_verdict ?? "unknown",
  ]));

  const tabBase = `/o/${org}/p/${project}/traces`;
  const baseParams = new URLSearchParams();
  // Reflect the *resolved* environment (cookie fallback included) so paginated
  // and refresh links keep the same filter the user is actually seeing.
  if (environment) baseParams.set("environment", environment);
  else if (qp.environment === "") baseParams.set("environment", "");
  if (qp.name && tab !== "rag") baseParams.set("name", qp.name);
  if (qp.status && tab !== "errors" && tab !== "partial") baseParams.set("status", qp.status);
  if (verdictFilter) baseParams.set("verdict", verdictFilter);
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
  // Period, tag, user, model, score and failures live behind "Mais filtros"; q and conversation show as chips.
  const advancedFilterCount = (["since", "until", "tag", "user_ref", "model", "score_lt", "failed"] as const).filter((key) => filters[key]).length;
  const hasFilters = Boolean(qp.name || qp.status || verdictFilter || Object.keys(filters).length > 0);
  const clearParams = new URLSearchParams();
  if (environment) clearParams.set("environment", environment);
  if (tab !== "all") clearParams.set("tab", tab);
  const clearFiltersHref = clearParams.toString() ? `${tabBase}?${clearParams}` : tabBase;

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1 className="page-header__title">Traces</h1>
          <div className="page-header__subtitle">Cada trace é uma execução da IA, do pedido à resposta</div>
        </div>
        <div className="page-header__actions">
          {autoRefreshEnabled ? (
            <span className="env-chip" title="Auto-refresh ativo">
              <span className="env-chip__dot" />
              ao vivo
            </span>
          ) : null}
          <Link href={`/o/${org}/p/${project}/traces/compare`} className="btn">
            <GitCompareArrows size={14} /> Comparar
          </Link>
          <Link href={exportsHref} className="btn">
            <Download size={14} /> Exportar
          </Link>
          <TracesAutoRefresh
            enabledByDefault={autoRefreshEnabled}
            intervalMs={30_000}
            disabledReason={autoRefreshDisabledReason}
          />
        </div>
      </header>

      <section className="card ops-traces__panel">
        <nav className="tabs" aria-label="Segmentos de traces">
          <Link href={tabHref("all")} className={`tab${tab === "all" ? " is-active" : ""}`} aria-current={tab === "all" ? "page" : undefined}>
            Todos
          </Link>
          <Link href={tabHref("errors")} className={`tab${tab === "errors" || tab === "partial" ? " is-active" : ""}`} aria-current={tab === "errors" || tab === "partial" ? "page" : undefined}>
            Com problema
          </Link>
          <Link href={tabHref("flagged")} className={`tab${tab === "flagged" ? " is-active" : ""}`} aria-current={tab === "flagged" ? "page" : undefined}>
            Marcados
          </Link>
          <Link href={tabHref("slow")} className={`tab${tab === "slow" ? " is-active" : ""}`} aria-current={tab === "slow" ? "page" : undefined}>
            <Clock size={13} /> Lentos
          </Link>
        </nav>

        {tab === "slow" ? (
          <nav className="tabs tabs--sub" aria-label="Origem da lentidão" data-testid="slow-kind-tabs">
            <Link href={slowKindHref("trace")} className={`tab${slowKind === "trace" ? " is-active" : ""}`}>Trace inteiro</Link>
            <Link href={slowKindHref("llm")} className={`tab${slowKind === "llm" ? " is-active" : ""}`}>LLM call</Link>
            <Link href={slowKindHref("retrieval")} className={`tab${slowKind === "retrieval" ? " is-active" : ""}`}>Retrieval</Link>
          </nav>
        ) : null}

        <form method="get" className="filters ops-traces__filters" action={tabBase}>
          {tab !== "all" ? <input type="hidden" name="tab" value={tab} /> : null}
          {tab === "slow" && slowKind !== "trace" ? <input type="hidden" name="slow_kind" value={slowKind} /> : null}
          {filters.q ? <input type="hidden" name="q" value={filters.q} /> : null}
          {filters.conversation_id ? <input type="hidden" name="conversation_id" value={filters.conversation_id} /> : null}
          <label className="filter-group">
            <Search size={13} />
            <input className="filter-input" name="name" defaultValue={qp.name ?? ""} placeholder="Buscar por nome" aria-label="Buscar por nome" />
          </label>
          <select className="filter-select" name="verdict" defaultValue={qp.verdict ?? ""} aria-label="Situação da avaliação">
            <option value="">Qualquer situação</option>
            <option value="approved">Aprovado</option>
            <option value="partial">Parcial</option>
            <option value="rejected">Reprovado</option>
            <option value="unknown">Sem dados</option>
          </select>
          <select className="filter-select" name="status" defaultValue={qp.status ?? ""} aria-label="Status de ingestão">
            <option value="">Qualquer status de ingestão</option>
            <option value="ok">ok</option>
            <option value="partial">parcial</option>
            <option value="error">erro</option>
          </select>
          <select className="filter-select" name="environment" defaultValue={environment ?? ""} aria-label="Ambiente">
            <option value="">Qualquer ambiente</option>
            <option value="prod">Produção</option>
            <option value="staging">Staging</option>
            <option value="dev">Desenvolvimento</option>
          </select>
          <Link
            href={tabHref("rag")}
            className={`btn${tab === "rag" ? " btn--primary" : ""}`}
            aria-current={tab === "rag" ? "page" : undefined}
            data-testid="trace-list-rag-tab"
          >
            <Layers size={14} /> RAG
          </Link>
          <button type="submit" className="btn">Aplicar</button>
          <details className="ops-traces__more" open={advancedFilterCount > 0}>
            <summary className="btn">
              Mais filtros{advancedFilterCount > 0 ? <span className="tab__count">{advancedFilterCount}</span> : null}
            </summary>
            <div className="ops-traces__more-body">
              <label className="filter-group ops-traces__date">
                <span>De</span>
                <input className="filter-input" type="date" name="since" defaultValue={filters.since ?? ""} aria-label="Desde (dia, UTC)" />
              </label>
              <label className="filter-group ops-traces__date">
                <span>Até</span>
                <input className="filter-input" type="date" name="until" defaultValue={filters.until ?? ""} aria-label="Até (dia, UTC)" />
              </label>
              <input className="filter-input" name="tag" defaultValue={filters.tag ?? ""} placeholder="Tag (canal:whatsapp)" aria-label="Tag no formato chave:valor" />
              <input className="filter-input" name="user_ref" defaultValue={filters.user_ref ?? ""} placeholder="Usuário" aria-label="Usuário" />
              <input className="filter-input" name="model" defaultValue={filters.model ?? ""} placeholder="Modelo (gpt-4o-mini)" aria-label="Modelo" />
              <input
                className="filter-input ops-traces__score"
                type="number"
                name="score_lt"
                min={0}
                max={1}
                step={0.05}
                defaultValue={filters.score_lt ?? ""}
                placeholder="Nota abaixo de"
                aria-label="Nota abaixo de (0 a 1)"
              />
              <label className="ops-traces__check">
                <input type="checkbox" name="failed" value="true" defaultChecked={Boolean(filters.failed)} />
                Só reprovados
              </label>
            </div>
          </details>
        </form>

        {filters.q || filters.conversation_id ? (
          <div className="ops-traces__chips">
            {filters.conversation_id ? (
              <span className="tag" data-testid="conversation-filter-chip">
                conversa: {filters.conversation_id}
                <Link href={withoutFilterHref("conversation_id")} aria-label="Remover filtro de conversa">
                  <X size={12} aria-hidden="true" />
                </Link>
              </span>
            ) : null}
            {filters.q ? (
              <span className="tag">
                busca: {filters.q}
                <Link href={withoutFilterHref("q")} aria-label="Remover busca">
                  <X size={12} aria-hidden="true" />
                </Link>
              </span>
            ) : null}
          </div>
        ) : null}

        {rows.length === 0 && hasFilters ? (
          <div className="empty ops-traces__empty">
            <div className="empty__title">Nenhum trace com esses filtros</div>
            <p className="empty__desc">Tente outro filtro ou limpe todos.</p>
            <Link href={clearFiltersHref} className="btn">Limpar filtros</Link>
          </div>
        ) : rows.length === 0 ? (
          <TracesEmpty project={project} />
        ) : (
          <TracesTable org={org} project={project} rows={rows} verdicts={verdicts} />
        )}
      </section>

      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          marginTop: 12,
          fontSize: 12,
          color: "var(--fg-3)",
        }}
      >
        <span>
          Mostrando {rows.length.toLocaleString("pt-BR")} trace{rows.length === 1 ? "" : "s"}
          {hasCursor ? " (próxima página)" : ""}
        </span>
        <div className="row" style={{ gap: 6 }}>
          {firstPageHref ? (
            <a href={firstPageHref} className="btn btn--sm btn--ghost" title="Voltar à primeira página">
              ‹
            </a>
          ) : (
            <button type="button" className="btn btn--sm btn--ghost" disabled>
              ‹
            </button>
          )}
          {nextPageHref ? (
            <a href={nextPageHref} className="btn btn--sm btn--ghost">
              ›
            </a>
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
