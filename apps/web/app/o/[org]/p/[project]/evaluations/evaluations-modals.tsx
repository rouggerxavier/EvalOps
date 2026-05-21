"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo } from "react";
import { ArrowUp, Play, Plus } from "lucide-react";

import { Metric } from "@/components/ui/Metric";
import { Modal } from "@/components/ui/Modal";
import {
  createRubricAction,
  publishRubricAction,
  triggerEvaluationAction,
} from "@/lib/actions";

export type EvaluationRowSummary = {
  rubric_id: string;
  slug: string;
  description: string | null;
  current_version: number;
  threshold: number;
  type_label: "LLM-judge" | "Heurística";
  judge_model: string | null;
  avg_score: number | null;
  runs_7d: number;
  pass_rate: number | null;
  yaml_source: string | null;
};

type RubricOption = {
  id: string;
  slug: string;
  current_version: number;
};

type TraceOption = {
  id: string;
  name: string;
  environment: string;
};

type Props = {
  org: string;
  project: string;
  projectId: string;
  rubrics: RubricOption[];
  traces: TraceOption[];
  drawerRow: EvaluationRowSummary | null;
};

function fmtPct(value: number | null): string {
  if (value === null || Number.isNaN(value)) return "—";
  return `${Math.round(value * 100)}%`;
}

export function EvaluationsModals({ org, project, projectId, rubrics, traces, drawerRow }: Props) {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const modal = params.get("modal");

  const close = useCallback(() => {
    const next = new URLSearchParams(Array.from(params.entries()));
    next.delete("modal");
    next.delete("rubric");
    const qs = next.toString();
    router.push(qs ? `${pathname}?${qs}` : pathname);
  }, [params, router, pathname]);

  const openPublish = useCallback(() => {
    const next = new URLSearchParams(Array.from(params.entries()));
    next.set("modal", "publish");
    if (drawerRow) next.set("rubric", drawerRow.rubric_id);
    router.push(`${pathname}?${next.toString()}`);
  }, [params, router, pathname, drawerRow]);

  const openRunForRubric = useCallback(() => {
    const next = new URLSearchParams(Array.from(params.entries()));
    next.set("modal", "run");
    if (drawerRow) next.set("rubric", drawerRow.rubric_id);
    router.push(`${pathname}?${next.toString()}`);
  }, [params, router, pathname, drawerRow]);

  const defaultRubricId = useMemo(
    () => params.get("rubric") ?? rubrics[0]?.id ?? "",
    [params, rubrics],
  );

  if (modal === "drawer" && drawerRow) {
    return (
      <Modal
        open
        onClose={close}
        title={drawerRow.slug}
        subtitle={drawerRow.description ?? "Rubric publicada"}
        width={640}
      >
        <div className="kpi-grid" style={{ gridTemplateColumns: "repeat(3, 1fr)", marginBottom: 0 }}>
          <Metric
            label="Tipo"
            value={drawerRow.type_label}
            delta={drawerRow.judge_model ?? "—"}
          />
          <Metric
            label="Score médio"
            value={drawerRow.avg_score === null ? "—" : drawerRow.avg_score.toFixed(2)}
            delta={`threshold ${drawerRow.threshold.toFixed(2)}`}
          />
          <Metric
            label="Runs 7d"
            value={drawerRow.runs_7d.toLocaleString("pt-BR")}
            delta={`pass ${fmtPct(drawerRow.pass_rate)}`}
            deltaTone="up"
          />
        </div>
        <div style={{ marginTop: 16 }}>
          <div className="faint mono" style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 8 }}>
            Rubric definition
          </div>
          <pre className="code">{drawerRow.yaml_source ?? "# YAML indisponível para esta versão."}</pre>
        </div>
        <div style={{ marginTop: 14, display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <button type="button" className="btn btn--sm" onClick={close}>Fechar</button>
          <button type="button" className="btn btn--sm" onClick={openPublish}>
            <ArrowUp size={11} /> Publicar v{drawerRow.current_version + 1}
          </button>
          <button type="button" className="btn btn--sm btn--primary" onClick={openRunForRubric}>
            <Play size={11} /> Rodar
          </button>
        </div>
      </Modal>
    );
  }

  if (modal === "run") {
    const canRun = rubrics.length > 0 && traces.length > 0;
    return (
      <Modal
        open
        onClose={close}
        title="Rodar avaliação"
        subtitle="Seleciona rubric e trace de produção para executar agora."
        width={520}
      >
        {!canRun ? (
          <p className="faint" style={{ fontSize: 13 }}>
            Precisa de pelo menos uma rubric publicada e um trace capturado.
          </p>
        ) : (
          <form action={triggerEvaluationAction} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <input type="hidden" name="org" value={org} />
            <input type="hidden" name="project" value={project} />
            <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 12, color: "var(--fg-3)" }}>
              <span>Rubric</span>
              <select name="rubric_id" defaultValue={defaultRubricId} className="filter-select">
                {rubrics.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.slug} (v{r.current_version})
                  </option>
                ))}
              </select>
            </label>
            <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 12, color: "var(--fg-3)" }}>
              <span>Trace</span>
              <select name="trace_id" defaultValue={traces[0]?.id} className="filter-select">
                {traces.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name} · {t.environment}
                  </option>
                ))}
              </select>
            </label>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
              <button type="button" className="btn btn--sm" onClick={close}>Cancelar</button>
              <button type="submit" className="btn btn--sm btn--primary">
                <Play size={11} /> Rodar agora
              </button>
            </div>
          </form>
        )}
      </Modal>
    );
  }

  if (modal === "create") {
    return (
      <Modal
        open
        onClose={close}
        title="Nova rubric"
        subtitle="Cole o YAML da rubric. Slug e evaluators são lidos do YAML."
        width={620}
      >
        <form action={createRubricAction} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <input type="hidden" name="org" value={org} />
          <input type="hidden" name="project" value={project} />
          <input type="hidden" name="project_id" value={projectId} />
          <input type="hidden" name="redirect_section" value="evaluations" />
          <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 12, color: "var(--fg-3)" }}>
            <span>YAML</span>
            <textarea
              name="yaml_source"
              required
              defaultValue={`slug: nova-rubrica\nversion: 1\nthreshold: 0.75\nevaluators:\n  - id: grounded_in_retrieval\n    type: builtin\n`}
              className="filter-input"
              style={{ minHeight: 240, fontFamily: "var(--font-mono)", fontSize: 12 }}
            />
          </label>
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
            <button type="button" className="btn btn--sm" onClick={close}>Cancelar</button>
            <button type="submit" className="btn btn--sm btn--primary">
              <Plus size={11} /> Criar rubric
            </button>
          </div>
        </form>
      </Modal>
    );
  }

  if (modal === "publish" && drawerRow) {
    return (
      <Modal
        open
        onClose={close}
        title={`Publicar v${drawerRow.current_version + 1}`}
        subtitle={drawerRow.slug}
        width={620}
      >
        <form action={publishRubricAction} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <input type="hidden" name="org" value={org} />
          <input type="hidden" name="project" value={project} />
          <input type="hidden" name="rubric_id" value={drawerRow.rubric_id} />
          <input type="hidden" name="redirect_section" value="evaluations" />
          <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 12, color: "var(--fg-3)" }}>
            <span>YAML da nova versão</span>
            <textarea
              name="yaml_source"
              required
              defaultValue={drawerRow.yaml_source ?? ""}
              className="filter-input"
              style={{ minHeight: 280, fontFamily: "var(--font-mono)", fontSize: 12 }}
            />
          </label>
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
            <button type="button" className="btn btn--sm" onClick={close}>Cancelar</button>
            <button type="submit" className="btn btn--sm btn--primary">
              <ArrowUp size={11} /> Publicar v{drawerRow.current_version + 1}
            </button>
          </div>
        </form>
      </Modal>
    );
  }

  return null;
}
