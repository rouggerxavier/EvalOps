"use client";

import type { CSSProperties, ReactNode } from "react";
import { useState } from "react";
import { Flag, GitCompare, Play, Target } from "lucide-react";

import { Modal } from "@/components/ui/Modal";
import {
  compareTracesAction,
  flagTraceAction,
  rerunTraceAction,
  triggerEvaluationAction,
} from "@/lib/actions";
import type { Rubric, Trace } from "@/lib/types";

type Props = {
  org: string;
  project: string;
  traceId: string;
  rubrics: Pick<Rubric, "id" | "slug" | "current_version">[];
  compareCandidates: Pick<Trace, "id" | "name">[];
};

const actionsStyle: CSSProperties = {
  display: "flex",
  justifyContent: "flex-end",
  gap: 8,
  marginTop: 16,
};

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: 4, marginBottom: 10 }}>
      <span style={{ fontSize: 11, color: "var(--fg-3)" }}>{label}</span>
      {children}
    </label>
  );
}

export function TraceHeaderActions({ org, project, traceId, rubrics, compareCandidates }: Props) {
  const [open, setOpen] = useState<null | "flag" | "rerun" | "compare" | "evaluate">(null);
  const close = () => setOpen(null);

  const hasRubric = rubrics.length > 0;
  const hasCompare = compareCandidates.length > 0;

  return (
    <>
      <button type="button" className="btn btn--sm" onClick={() => setOpen("flag")}>
        <Flag size={12} /> Flagear
      </button>
      <button type="button" className="btn btn--sm" onClick={() => setOpen("rerun")}>
        <Play size={12} /> Reexecutar
      </button>
      <button type="button" className="btn btn--sm" onClick={() => setOpen("compare")}>
        <GitCompare size={12} /> Comparar
      </button>
      <button type="button" className="btn btn--sm btn--primary" onClick={() => setOpen("evaluate")}>
        <Target size={12} /> Avaliar
      </button>

      <Modal open={open === "flag"} onClose={close} title="Flagear trace" subtitle="POST /v1/traces/{id}/flags">
        <form action={flagTraceAction}>
          <input type="hidden" name="org" value={org} />
          <input type="hidden" name="project" value={project} />
          <input type="hidden" name="trace_id" value={traceId} />
          <Field label="Motivo">
            <select className="filter-select" name="reason" defaultValue="manual">
              <option value="manual">manual</option>
              <option value="schema_mismatch">schema_mismatch</option>
              <option value="low_quality">low_quality</option>
            </select>
          </Field>
          <Field label="Nota (opcional)">
            <input className="filter-input" name="note" placeholder="contexto livre" style={{ height: 32, padding: "0 10px" }} />
          </Field>
          <div style={actionsStyle}>
            <button type="button" className="btn btn--sm" onClick={close}>Cancelar</button>
            <button type="submit" className="btn btn--sm btn--primary"><Flag size={12} /> Flagear</button>
          </div>
        </form>
      </Modal>

      <Modal open={open === "rerun"} onClose={close} title="Reexecutar trace" subtitle="POST /v1/traces/{id}/rerun">
        <form action={rerunTraceAction}>
          <input type="hidden" name="org" value={org} />
          <input type="hidden" name="project" value={project} />
          <input type="hidden" name="trace_id" value={traceId} />
          <Field label="Modelo (opcional)">
            <input className="filter-input" name="model" placeholder="ex: gpt-4o-mini" style={{ height: 32, padding: "0 10px" }} />
          </Field>
          <Field label="Variáveis JSON (opcional)">
            <input className="filter-input" name="variables_json" placeholder="{}" defaultValue="{}" style={{ height: 32, padding: "0 10px", fontFamily: "var(--font-mono)" }} />
          </Field>
          <div style={actionsStyle}>
            <button type="button" className="btn btn--sm" onClick={close}>Cancelar</button>
            <button type="submit" className="btn btn--sm btn--primary"><Play size={12} /> Reexecutar</button>
          </div>
        </form>
      </Modal>

      <Modal open={open === "compare"} onClose={close} title="Comparar com outro trace" subtitle="POST /v1/traces/compare">
        <form action={compareTracesAction}>
          <input type="hidden" name="org" value={org} />
          <input type="hidden" name="project" value={project} />
          <input type="hidden" name="left_trace_id" value={traceId} />
          <Field label="Trace direito">
            <select className="filter-select" name="right_trace_id" required disabled={!hasCompare}>
              {compareCandidates.map((t) => (
                <option key={t.id} value={t.id}>{t.name} · {t.id.slice(0, 8)}</option>
              ))}
              {!hasCompare ? <option value="">Sem traces candidatos</option> : null}
            </select>
          </Field>
          <div style={actionsStyle}>
            <button type="button" className="btn btn--sm" onClick={close}>Cancelar</button>
            <button type="submit" className="btn btn--sm btn--primary" disabled={!hasCompare}>
              <GitCompare size={12} /> Comparar
            </button>
          </div>
        </form>
      </Modal>

      <Modal open={open === "evaluate"} onClose={close} title="Rodar avaliação" subtitle="POST /v1/evaluations/run">
        <form action={triggerEvaluationAction}>
          <input type="hidden" name="return_to" value="trace" />
          <input type="hidden" name="org" value={org} />
          <input type="hidden" name="project" value={project} />
          <input type="hidden" name="trace_id" value={traceId} />
          <Field label="Rubrica">
            <select className="filter-select" name="rubric_id" required disabled={!hasRubric}>
              {rubrics.map((r) => (
                <option key={r.id} value={r.id}>{r.slug} · v{r.current_version}</option>
              ))}
              {!hasRubric ? <option value="">Nenhuma rubrica cadastrada</option> : null}
            </select>
          </Field>
          <div style={actionsStyle}>
            <button type="button" className="btn btn--sm" onClick={close}>Cancelar</button>
            <button type="submit" className="btn btn--sm btn--primary" disabled={!hasRubric}>
              <Target size={12} /> Avaliar
            </button>
          </div>
        </form>
      </Modal>
    </>
  );
}
