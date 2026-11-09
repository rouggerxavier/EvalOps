"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { ChevronRight, Flag, GitCompareArrows } from "lucide-react";

import { StatusBadge } from "@/components/ui/Badge";
import { Copyable } from "@/components/ui/Copyable";
import { Modal } from "@/components/ui/Modal";
import { ScoreCell } from "@/components/ui/ScoreCell";
import { projectHref } from "@/components/app-shell-nav";
import { bulkFlagTracesAction } from "@/lib/actions";
import { formatCost, formatLatency, formatRelativeTime } from "@/lib/format";
import {
  getTraceModelLabel,
  isTraceRagCandidate,
} from "@/lib/trace-display";
import type { Trace } from "@/lib/types";
import { EvaluationStatus, type EvaluationVerdict } from "./trace-status";

type Props = {
  canWrite: boolean;
  org: string;
  project: string;
  rows: Trace[];
  verdicts: Record<string, EvaluationVerdict | null>;
  environment?: string;
};

export function TracesTable({ org, project, rows, verdicts, environment, canWrite }: Props) {
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const [modalOpen, setModalOpen] = useState(false);

  const allChecked = rows.length > 0 && selected.size === rows.length;
  const indeterminate = selected.size > 0 && selected.size < rows.length;

  function toggleOne(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAll() {
    setSelected((prev) => (prev.size === rows.length ? new Set() : new Set(rows.map((r) => r.id))));
  }

  const selectedIds = useMemo(() => Array.from(selected), [selected]);

  return (
    <>
      {selectedIds.length > 0 ? (
        <div
          className="row ops-traces__selection"
          style={{
            position: "sticky",
            top: 0,
            zIndex: 5,
            justifyContent: "space-between",
            padding: "10px 12px",
            background: "var(--surface-2)",
            border: "1px solid var(--border-default)",
            borderRadius: "var(--r-sm)",
            marginBottom: 8,
          }}
        >
          <span className="mono" style={{ fontSize: 12 }}>
            {selectedIds.length} selecionado{selectedIds.length === 1 ? "" : "s"}
          </span>
          <div className="row" style={{ gap: 6 }}>
            <button type="button" className="btn btn--sm" onClick={() => setSelected(new Set())}>
              Limpar
            </button>
            {selectedIds.length === 2 ? (
              <Link
                href={`/o/${org}/p/${project}/traces/compare?left=${encodeURIComponent(selectedIds[0])}&right=${encodeURIComponent(selectedIds[1])}${environment === undefined ? "" : `&environment=${encodeURIComponent(environment)}`}`}
                className="btn btn--sm"
              >
                <GitCompareArrows size={12} /> Comparar
              </Link>
            ) : null}
            {canWrite ? <button type="button" className="btn btn--sm btn--primary" onClick={() => setModalOpen(true)}>
              <Flag size={12} /> Flagear em lote
            </button> : null}
          </div>
        </div>
      ) : null}

      <div className="table-wrap ops-traces__table-scroll">
        <table className="t ops-traces__table">
          <thead>
            <tr>
              <th style={{ width: 28 }}>
                <input
                  type="checkbox"
                  aria-label="Selecionar todos"
                  checked={allChecked}
                  ref={(el) => {
                    if (el) el.indeterminate = indeterminate;
                  }}
                  onChange={toggleAll}
                  style={{ accentColor: "var(--primary-400)" }}
                />
              </th>
              <th>Situação</th>
              <th>Nome</th>
              <th>Modelo</th>
              <th className="t__num">Duração</th>
              <th className="t__num">Tokens</th>
              <th className="t__num">Custo</th>
              <th className="t__num">Score</th>
              <th>Quando</th>
              <th style={{ width: 28 }} />
            </tr>
          </thead>
          <tbody>
            {rows.map((trace) => {
              const model = getTraceModelLabel(trace);
              const isRag = isTraceRagCandidate(trace);
              const isChecked = selected.has(trace.id);
              const verdict = verdicts[trace.id] ?? null;
              const href = projectHref(`/o/${org}/p/${project}/traces`, `/${trace.id}`, environment);
              return (
                <tr
                  key={trace.id}
                  className={verdict === "rejected" ? "is-flagged" : ""}
                >
                  <td onClick={(e) => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      aria-label={`Selecionar ${trace.name}`}
                      checked={isChecked}
                      onChange={() => toggleOne(trace.id)}
                      style={{ accentColor: "var(--primary-400)" }}
                    />
                  </td>
                  <td>
                    <EvaluationStatus verdict={verdict} />
                    <span className="ops-traces__ingestion">Ingestão · <StatusBadge status={trace.status} /></span>
                  </td>
                  <td>
                    <Link href={href} className="ops-traces__name-link">{trace.name}</Link>
                    <div className="ops-traces__trace-meta">
                      <Copyable value={trace.id} display={trace.id.slice(0, 12)} />
                      <span>{trace.environment}</span>
                      {trace.service ?? "—"}
                      {isRag ? <span>RAG</span> : null}
                      {trace.flag_count ? <span>marcado</span> : null}
                      {trace.redacted ? <span>redigido</span> : null}
                    </div>
                  </td>
                  <td className="t__mono">{model ?? "—"}</td>
                  <td
                    className="t__num"
                    style={{
                      color:
                        trace.duration_ms > 4000
                          ? "var(--danger)"
                          : trace.duration_ms > 2000
                          ? "var(--warning)"
                          : "var(--fg-2)",
                    }}
                  >
                    <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 2 }}>
                      <span>{formatLatency(trace.duration_ms)}</span>
                      {trace.slow_reason === "llm" || trace.slow_reason === "retrieval" ? (
                        <span
                          className="tag"
                          title={
                            trace.slow_reason === "llm"
                              ? "Span LLM ultrapassou o limiar de lentidão"
                              : "Span de retrieval ultrapassou o limiar de lentidão"
                          }
                          style={{ fontSize: 9, padding: "1px 4px" }}
                        >
                          {trace.slow_reason === "llm" ? "LLM lento" : "retrieval lento"}
                        </span>
                      ) : null}
                    </div>
                  </td>
                  <td className="t__num t__muted">
                    {(trace.total_tokens_in + trace.total_tokens_out).toLocaleString("pt-BR")}
                    <span className="ops-traces__token-detail">
                      {trace.total_tokens_in.toLocaleString("pt-BR")} entrada · {trace.total_tokens_out.toLocaleString("pt-BR")} saída
                    </span>
                  </td>
                  <td className="t__num">
                    <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 2 }}>
                      <span>{formatCost(trace.total_cost_usd)}</span>
                      {trace.cost_source && trace.cost_source !== "priced" ? (
                        <span
                          className="tag"
                          title={
                            trace.cost_source === "unpriced"
                              ? "Tokens registrados, mas provider/model sem preço — custo não é uma medição real"
                              : trace.cost_source === "provided"
                                ? "Valor enviado pelo cliente"
                                : "Sem tokens nem preço — custo desconhecido"
                          }
                          style={{ fontSize: 9, padding: "1px 4px" }}
                        >
                          {trace.cost_source === "unpriced" ? "sem preço" : trace.cost_source === "provided" ? "informado" : "sem dados"}
                        </span>
                      ) : null}
                    </div>
                  </td>
                  <td className="t__num">
                    {trace.last_score === null || trace.last_score === undefined ? (
                      <span className="t__faint">Sem dados</span>
                    ) : (
                      <ScoreCell value={trace.last_score} />
                    )}
                  </td>
                  <td className="t__faint" style={{ fontSize: 11 }}>
                    {formatRelativeTime(trace.created_at)}
                  </td>
                  <td>
                    <Link href={href}>
                      <ChevronRight size={12} className="t__chev" />
                    </Link>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <Modal
        open={canWrite && modalOpen}
        onClose={() => setModalOpen(false)}
        title="Flagear traces selecionados"
        subtitle={`${selectedIds.length} trace(s) · POST /v1/traces/bulk-flag`}
      >
        <form action={bulkFlagTracesAction}>
          <input type="hidden" name="org" value={org} />
          <input type="hidden" name="project" value={project} />
          {selectedIds.map((id) => (
            <input type="hidden" name="trace_ids" value={id} key={id} />
          ))}
          <label style={{ display: "flex", flexDirection: "column", gap: 4, marginBottom: 10 }}>
            <span style={{ fontSize: 11, color: "var(--fg-3)" }}>Motivo</span>
            <select className="filter-select" name="reason" defaultValue="manual">
              <option value="manual">manual</option>
              <option value="schema_mismatch">schema_mismatch</option>
              <option value="low_quality">low_quality</option>
            </select>
          </label>
          <label style={{ display: "flex", flexDirection: "column", gap: 4, marginBottom: 10 }}>
            <span style={{ fontSize: 11, color: "var(--fg-3)" }}>Nota (opcional)</span>
            <input className="filter-input" name="note" placeholder="contexto livre" style={{ height: 32, padding: "0 10px" }} />
          </label>
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 16 }}>
            <button type="button" className="btn btn--sm" onClick={() => setModalOpen(false)}>
              Cancelar
            </button>
            <button type="submit" className="btn btn--sm btn--primary" disabled={selectedIds.length === 0}>
              <Flag size={12} /> Flagear {selectedIds.length}
            </button>
          </div>
        </form>
      </Modal>
    </>
  );
}

type EmptyProps = { project: string };
export function TracesEmpty({ project }: EmptyProps) {
  return (
    <div className="empty">
      <div className="empty__title">Nenhum trace encontrado</div>
      <div className="empty__desc">
        Ajuste os filtros ou conecte o SDK para capturar tráfego.
      </div>
      <pre className="empty__code">{`import evalops
evalops.init(api_key="evk_prod_...", project="${project}", environment="prod")

@evalops.trace("chat.answer")
def answer(msg: str): ...`}</pre>
    </div>
  );
}
