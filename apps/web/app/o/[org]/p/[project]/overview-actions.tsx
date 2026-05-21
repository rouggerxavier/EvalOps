"use client";

import type { CSSProperties, ReactNode } from "react";
import { useState } from "react";
import { ArrowRight, Download, GitCompare, Play } from "lucide-react";

import { Modal } from "@/components/ui/Modal";
import {
  createExportAction,
  triggerEvaluationFromOverviewAction,
} from "@/lib/actions";
import type { Rubric, Trace } from "@/lib/types";

type Context = {
  org: string;
  project: string;
  projectId: string;
  environment?: string;
  rubrics: Pick<Rubric, "id" | "slug" | "current_version">[];
  candidateTraces: Pick<Trace, "id" | "name">[];
};

const rowStyle: CSSProperties = {
  display: "flex",
  gap: 10,
  alignItems: "center",
  padding: "8px 10px",
  border: "1px solid var(--border-subtle)",
  borderRadius: "var(--r-sm)",
  background: "var(--surface-2)",
  cursor: "pointer",
  textAlign: "left",
  width: "100%",
  color: "inherit",
  textDecoration: "none",
};

const iconBoxStyle: CSSProperties = {
  width: 28,
  height: 28,
  borderRadius: "var(--r-sm)",
  background: "rgba(59, 141, 245, 0.14)",
  border: "1px solid rgba(59, 141, 245, 0.32)",
  display: "grid",
  placeItems: "center",
  color: "var(--primary-400)",
  flexShrink: 0,
};

const actionsStyle: CSSProperties = {
  display: "flex",
  justifyContent: "flex-end",
  gap: 8,
  marginTop: 16,
};

function Row({
  icon,
  title,
  desc,
  onClick,
  href,
}: {
  icon: ReactNode;
  title: ReactNode;
  desc: ReactNode;
  onClick?: () => void;
  href?: string;
}) {
  const content = (
    <>
      <span style={iconBoxStyle}>{icon}</span>
      <span style={{ flex: 1, minWidth: 0 }}>
        <span style={{ display: "block", fontSize: 12.5, fontWeight: 500, color: "var(--fg-1)" }}>{title}</span>
        <span style={{ display: "block", fontSize: 11, color: "var(--fg-4)" }}>{desc}</span>
      </span>
      <ArrowRight size={11} style={{ color: "var(--fg-4)" }} />
    </>
  );
  if (href) {
    return (
      <a href={href} style={rowStyle}>
        {content}
      </a>
    );
  }
  return (
    <button type="button" onClick={onClick} style={rowStyle}>
      {content}
    </button>
  );
}

function FieldRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: 4, marginBottom: 10 }}>
      <span style={{ fontSize: 11, color: "var(--fg-3)" }}>{label}</span>
      {children}
    </label>
  );
}

function EvaluateForm({ ctx, onCancel }: { ctx: Context; onCancel: () => void }) {
  const hasRubric = ctx.rubrics.length > 0;
  const hasTrace = ctx.candidateTraces.length > 0;
  return (
    <form action={triggerEvaluationFromOverviewAction}>
      <input type="hidden" name="org" value={ctx.org} />
      <input type="hidden" name="project" value={ctx.project} />
      <FieldRow label="Rubrica">
        <select className="filter-select" name="rubric_id" required disabled={!hasRubric}>
          {ctx.rubrics.map((r) => (
            <option key={r.id} value={r.id}>{r.slug} · v{r.current_version}</option>
          ))}
          {!hasRubric ? <option value="">Nenhuma rubrica cadastrada</option> : null}
        </select>
      </FieldRow>
      <FieldRow label="Trace alvo">
        <select className="filter-select" name="trace_id" required disabled={!hasTrace}>
          {ctx.candidateTraces.map((t) => (
            <option key={t.id} value={t.id}>{t.name} · {t.id.slice(0, 8)}</option>
          ))}
          {!hasTrace ? <option value="">Sem trace flagged recente</option> : null}
        </select>
      </FieldRow>
      <div style={actionsStyle}>
        <button type="button" className="btn btn--sm" onClick={onCancel}>Cancelar</button>
        <button type="submit" className="btn btn--sm btn--primary" disabled={!hasRubric || !hasTrace}>
          <Play size={12} /> Rodar
        </button>
      </div>
    </form>
  );
}

function ExportForm({ ctx, onCancel }: { ctx: Context; onCancel: () => void }) {
  return (
    <form action={createExportAction}>
      <input type="hidden" name="org" value={ctx.org} />
      <input type="hidden" name="project" value={ctx.project} />
      <input type="hidden" name="project_id" value={ctx.projectId} />
      {ctx.environment ? <input type="hidden" name="environment" value={ctx.environment} /> : null}
      <input type="hidden" name="status" value="error" />
      <p style={{ fontSize: 12, color: "var(--fg-3)", margin: 0 }}>
        Cria export JSONL com filtro <code className="mono">status=error</code>
        {ctx.environment ? <> e <code className="mono">env={ctx.environment}</code></> : null}.
      </p>
      <div style={actionsStyle}>
        <button type="button" className="btn btn--sm" onClick={onCancel}>Cancelar</button>
        <button type="submit" className="btn btn--sm btn--primary">
          <Download size={12} /> Criar export
        </button>
      </div>
    </form>
  );
}

export function EvaluateHeaderButton({ ctx }: { ctx: Context }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" className="btn btn--sm btn--primary" onClick={() => setOpen(true)}>
        <Play size={12} /> Rodar avaliação
      </button>
      <Modal open={open} onClose={() => setOpen(false)} title="Rodar avaliação" subtitle="Selecione rubrica e trace alvo">
        <EvaluateForm ctx={ctx} onCancel={() => setOpen(false)} />
      </Modal>
    </>
  );
}

export function OverviewSuggestions({ ctx }: { ctx: Context }) {
  const [open, setOpen] = useState<null | "evaluate" | "export">(null);
  const close = () => setOpen(null);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <Row
        icon={<Play size={12} />}
        title="Rodar avaliação no trace flagged mais recente"
        desc={
          ctx.candidateTraces.length > 0
            ? `${ctx.candidateTraces.length} trace(s) flagged disponíveis`
            : "Sem trace flagged na janela"
        }
        onClick={() => setOpen("evaluate")}
      />
      <Row
        icon={<GitCompare size={12} />}
        title="Criar experimento A/B"
        desc="Comparar variantes contra a baseline atual"
        href={`/o/${ctx.org}/p/${ctx.project}/experiments`}
      />
      <Row
        icon={<Download size={12} />}
        title="Exportar erros para fine-tune"
        desc="Gera JSONL com traces status=error"
        onClick={() => setOpen("export")}
      />

      <Modal open={open === "evaluate"} onClose={close} title="Rodar avaliação" subtitle="Selecione rubrica e trace alvo">
        <EvaluateForm ctx={ctx} onCancel={close} />
      </Modal>
      <Modal open={open === "export"} onClose={close} title="Exportar erros" subtitle="POST /v1/exports">
        <ExportForm ctx={ctx} onCancel={close} />
      </Modal>
    </div>
  );
}

export function WindowSelect({
  org,
  project,
  current,
  environment,
}: {
  org: string;
  project: string;
  current: "24h" | "7d" | "30d";
  environment?: string;
}) {
  return (
    <form method="get" action={`/o/${org}/p/${project}`} style={{ display: "inline-flex" }}>
      {environment ? <input type="hidden" name="environment" value={environment} /> : null}
      <select
        className="filter-select"
        name="window"
        defaultValue={current}
        onChange={(e) => e.currentTarget.form?.requestSubmit()}
      >
        <option value="24h">Últimas 24h</option>
        <option value="7d">Últimos 7 dias</option>
        <option value="30d">Últimos 30 dias</option>
      </select>
      <noscript>
        <button type="submit" className="btn btn--sm">Aplicar</button>
      </noscript>
    </form>
  );
}
