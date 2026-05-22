"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { ChevronRight, Flag } from "lucide-react";

import { StatusBadge } from "@/components/ui/Badge";
import { Copyable } from "@/components/ui/Copyable";
import { Modal } from "@/components/ui/Modal";
import { ScoreCell } from "@/components/ui/ScoreCell";
import { bulkFlagTracesAction } from "@/lib/actions";
import { formatCost, formatLatency, formatRelativeTime } from "@/lib/format";
import {
  formatTraceScore,
  getTraceModelLabel,
  isTraceRagCandidate,
} from "@/lib/trace-display";
import type { Trace } from "@/lib/types";

type Props = {
  org: string;
  project: string;
  rows: Trace[];
};

export function TracesTable({ org, project, rows }: Props) {
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
          className="row"
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
            <button type="button" className="btn btn--sm btn--primary" onClick={() => setModalOpen(true)}>
              <Flag size={12} /> Flagear em lote
            </button>
          </div>
        </div>
      ) : null}

      <div className="table-wrap">
        <table className="t">
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
              <th>Nome</th>
              <th>Trace ID</th>
              <th>Status</th>
              <th>Env</th>
              <th>Modelo</th>
              <th className="t__num">Duração</th>
              <th className="t__num">Tokens</th>
              <th className="t__num">Custo</th>
              <th>Score</th>
              <th>Quando</th>
              <th style={{ width: 28 }} />
            </tr>
          </thead>
          <tbody>
            {rows.map((trace) => {
              const model = getTraceModelLabel(trace);
              const isRag = isTraceRagCandidate(trace);
              const isChecked = selected.has(trace.id);
              const href = `/o/${org}/p/${project}/traces/${trace.id}`;
              return (
                <tr
                  key={trace.id}
                  className={trace.status !== "ok" ? "is-flagged" : ""}
                  style={{ cursor: "pointer" }}
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
                    <Link href={href} style={{ display: "flex", flexDirection: "column", gap: 1, color: "inherit", textDecoration: "none" }}>
                      <span className="t__name">{trace.name}</span>
                      <span className="t__faint mono" style={{ fontSize: 10 }}>
                        {trace.service ?? "—"}
                        {isRag ? <> · <span style={{ color: "var(--info)" }}>RAG</span></> : null}
                      </span>
                    </Link>
                  </td>
                  <td onClick={(e) => e.stopPropagation()}>
                    <Copyable value={trace.id} display={`${trace.id.slice(0, 14)}…`} />
                  </td>
                  <td>
                    <div className="row" style={{ gap: 6 }}>
                      <StatusBadge status={trace.status} />
                      {trace.redacted ? <span className="tag">redigido</span> : null}
                    </div>
                  </td>
                  <td>
                    <span className="tag">{trace.environment}</span>
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
                    {trace.total_tokens_in.toLocaleString("pt-BR")}
                    <span className="faint">/{trace.total_tokens_out.toLocaleString("pt-BR")}</span>
                  </td>
                  <td className="t__num">{formatCost(trace.total_cost_usd)}</td>
                  <td>
                    {trace.last_score === null || trace.last_score === undefined ? (
                      <span className="faint mono">—</span>
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
        open={modalOpen}
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
