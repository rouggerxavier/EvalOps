import Link from "next/link";
import { Clock, Download, GitCompareArrows, Layers, Search } from "lucide-react";

import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { getActiveEnvironment } from "@/lib/active-env";
import { getProjectEvaluations, getTraces, hasAuthToken, resolveProject } from "@/lib/api";
import type { EvaluationRun } from "@/lib/types";

import { TracesAutoRefresh } from "./traces-auto-refresh";
import { TracesEmpty, TracesTable } from "./traces-table";
import { evaluationVerdict } from "./trace-status";

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
  }>;
};

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
  const [traces, evaluations] = await Promise.all([
    getTraces({
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
    }),
    getProjectEvaluations(resolved.project_id, 100, environment).catch(() => ({ data: [] })),
  ]);

  const verdictFilter = ["approved", "partial", "rejected", "unknown"].includes(qp.verdict ?? "")
    ? qp.verdict
    : undefined;
  const rows = traces.data;
  const latestEvaluationByTrace = new Map<string, EvaluationRun>();
  for (const run of evaluations.data) {
    if (!latestEvaluationByTrace.has(run.trace_id)) latestEvaluationByTrace.set(run.trace_id, run);
  }
  const verdicts = Object.fromEntries(rows.map((trace) => [
    trace.id,
    evaluationVerdict(latestEvaluationByTrace.get(trace.id)),
  ]));
  const displayRows = rows.filter((trace) => {
    if (!verdictFilter) return true;
    const verdict = verdicts[trace.id];
    return verdictFilter === "unknown"
      ? verdict === null || verdict === "unknown"
      : verdict === verdictFilter;
  });

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
  const hasFilters = Boolean(qp.name || qp.status || verdictFilter);
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
          <select className="filter-select" aria-label="Período" disabled defaultValue="">
            <option value="">Período sem dados na API</option>
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
        </form>

        {displayRows.length === 0 && hasFilters ? (
          <div className="empty ops-traces__empty">
            <div className="empty__title">Nenhum trace com esses filtros</div>
            <p className="empty__desc">Tente outro nome ou situação, ou limpe os filtros.</p>
            <Link href={clearFiltersHref} className="btn">Limpar filtros</Link>
          </div>
        ) : displayRows.length === 0 ? (
          <TracesEmpty project={project} />
        ) : (
          <TracesTable org={org} project={project} rows={displayRows} verdicts={verdicts} />
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
