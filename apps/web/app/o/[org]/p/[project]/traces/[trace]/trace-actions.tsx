"use client";

import type { CSSProperties, ReactNode } from "react";
import { useEffect, useRef, useState } from "react";
import { useFormState, useFormStatus } from "react-dom";
import { EyeOff, Flag, GitCompare, Play, Target } from "lucide-react";

import { Modal } from "@/components/ui/Modal";
import {
  compareTracesAction,
  flagTraceAction,
  hideTraceAction,
  rerunTraceAction,
  triggerEvaluationAction,
} from "@/lib/actions";
import type { Rubric, Trace } from "@/lib/types";

type Props = {
  canWrite: boolean;
  canDestructive: boolean;
  org: string;
  project: string;
  traceId: string;
  rubrics: Pick<Rubric, "id" | "slug" | "current_version">[];
  compareCandidates: Pick<Trace, "id" | "name">[];
  flagged: boolean;
  environment?: string;
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

function HideSubmit() {
  const { pending } = useFormStatus();
  return <button type="submit" className="btn btn--danger" disabled={pending}>{pending ? "Ocultando…" : "Ocultar trace"}</button>;
}

function HideTraceConfirmation({ org, project, traceId, environment, onClose }: Pick<Props, "org" | "project" | "traceId" | "environment"> & { onClose: () => void }) {
  const [state, action] = useFormState(hideTraceAction, { error: null });
  const content = useRef<HTMLFormElement>(null);
  useEffect(() => {
    const dialog = content.current?.closest<HTMLElement>('[role="dialog"]');
    const previousFocus = document.activeElement as HTMLElement | null;
    if (!dialog) return;
    dialog.setAttribute("aria-label", "Ocultar trace?");
    dialog.setAttribute("aria-describedby", "hide-trace-description");
    content.current?.querySelector<HTMLButtonElement>('[data-cancel]')?.focus();
    const trapFocus = (event: KeyboardEvent) => {
      if (event.key !== "Tab") return;
      const buttons = Array.from(dialog.querySelectorAll<HTMLElement>('button:not(:disabled), a[href]'));
      const first = buttons[0];
      const last = buttons[buttons.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    };
    dialog.addEventListener("keydown", trapFocus);
    return () => { dialog.removeEventListener("keydown", trapFocus); previousFocus?.focus(); };
  }, []);
  return (
    <Modal open onClose={onClose} title="Ocultar trace?">
      <form ref={content} action={action}>
        <p id="hide-trace-description">O trace sairá da lista e seu detalhe ficará indisponível. Avaliações históricas, cópias em datasets, exports, auditoria e backups têm vida própria e não são apagados por esta ação.</p>
        <input type="hidden" name="org" value={org} />
        <input type="hidden" name="project" value={project} />
        <input type="hidden" name="trace_id" value={traceId} />
        {environment !== undefined ? <input type="hidden" name="environment" value={environment} /> : null}
        {state.error ? <p role="alert" style={{ color: "var(--danger)" }}>{state.error}</p> : null}
        <div style={actionsStyle}>
          <button type="button" className="btn" data-cancel onClick={onClose}>Cancelar</button>
          <HideSubmit />
        </div>
      </form>
    </Modal>
  );
}

export function TraceHeaderActions({ org, project, traceId, rubrics, compareCandidates, flagged, environment, canWrite, canDestructive }: Props) {
  const [open, setOpen] = useState<null | "flag" | "rerun" | "compare" | "evaluate" | "hide">(null);
  const close = () => setOpen(null);

  const hasRubric = rubrics.length > 0;
  const hasCompare = compareCandidates.length > 0;

  return (
    <>
      {canDestructive ? <button type="button" className="btn" onClick={() => setOpen("hide")}><EyeOff size={14} aria-hidden="true" /> Ocultar trace</button> : null}
      {canDestructive && open === "hide" ? <HideTraceConfirmation org={org} project={project} traceId={traceId} environment={environment} onClose={close} /> : null}
      <button type="button" className="btn" onClick={() => setOpen("compare")}>
        <GitCompare size={14} /> Comparar
      </button>
      {flagged ? (
        <span className="ops-status ops-status--partial"><Flag size={13} aria-hidden="true" /> Marcado para revisão</span>
      ) : canWrite ? (
        <button type="button" className="btn" onClick={() => setOpen("flag")}>
          <Flag size={14} /> Marcar para revisão
        </button>
      ) : null}
      {canWrite ? <button type="button" className="btn" onClick={() => setOpen("rerun")}>
        <Play size={12} /> Repetir chamada LLM
      </button> : null}
      {canWrite ? <button type="button" className="btn btn--primary" onClick={() => setOpen("evaluate")}>
        <Target size={12} /> Avaliar
      </button> : null}

      <Modal open={canWrite && open === "flag"} onClose={close} title="Flagear trace" subtitle="POST /v1/traces/{id}/flags">
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

      <Modal open={canWrite && open === "rerun"} onClose={close} title="Repetir chamada LLM" subtitle="Repete uma chamada de modelo. Não executa o agente completo e pode consumir orçamento.">
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
            <button type="submit" className="btn btn--sm btn--primary"><Play size={12} /> Repetir chamada LLM</button>
          </div>
        </form>
      </Modal>

      <Modal open={open === "compare"} onClose={close} title="Comparar com outro trace" subtitle="POST /v1/traces/compare">
        <form action={compareTracesAction}>
          {environment !== undefined ? <input type="hidden" name="environment" value={environment} /> : null}
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

      <Modal open={canWrite && open === "evaluate"} onClose={close} title="Rodar avaliação" subtitle="POST /v1/evaluations/run">
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
