import Link from "next/link";
import { GitBranch, Plus } from "lucide-react";

import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { createPromptAction, createPromptVersionAction } from "@/lib/actions";
import { getPromptUsage, getPromptVersions, getPrompts, hasAuthToken, resolveProject } from "@/lib/api";
import type { PromptVersion } from "@/lib/types";

type Props = {
  params: Promise<{ org: string; project: string }>;
  searchParams: Promise<{ prompt?: string; created?: string; versioned?: string; error?: string }>;
};

function relTime(iso: string): string {
  const diff = Date.now() - Date.parse(iso);
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "agora";
  if (mins < 60) return `${mins}m atrás`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h atrás`;
  return `${Math.floor(hrs / 24)}d atrás`;
}

function DiffView({ current, previous }: { current: PromptVersion; previous: PromptVersion | null }) {
  const currLines = current.template.split("\n");

  if (!previous) {
    return (
      <div style={{ padding: "12px 0" }}>
        {currLines.map((line, i) => (
          <div
            key={i}
            style={{
              display: "flex",
              padding: "0 16px",
              fontFamily: "var(--font-mono)",
              fontSize: 12,
              lineHeight: "22px",
              background: "rgba(34,211,168,0.06)",
              borderLeft: "2px solid var(--ok)",
            }}
          >
            <span style={{ width: 16, color: "var(--ok)", userSelect: "none" }}>+</span>
            <span style={{ color: "var(--text-dim)", whiteSpace: "pre-wrap", wordBreak: "break-all" }}>
              {line || " "}
            </span>
          </div>
        ))}
      </div>
    );
  }

  const prevLines = previous.template.split("\n");
  const maxLen = Math.max(currLines.length, prevLines.length);
  const lines: Array<{ text: string; kind: "add" | "del" | "same" }> = [];

  for (let i = 0; i < maxLen; i++) {
    const c = currLines[i];
    const p = prevLines[i];
    if (c === p) {
      if (c !== undefined) lines.push({ text: c, kind: "same" });
    } else {
      if (p !== undefined) lines.push({ text: p, kind: "del" });
      if (c !== undefined) lines.push({ text: c, kind: "add" });
    }
  }

  return (
    <div style={{ padding: "12px 0" }}>
      {lines.map((line, i) => {
        const isAdd = line.kind === "add";
        const isDel = line.kind === "del";
        return (
          <div
            key={i}
            style={{
              display: "flex",
              padding: "0 16px",
              background: isAdd
                ? "rgba(34,211,168,0.08)"
                : isDel
                ? "rgba(255,107,107,0.08)"
                : "transparent",
              borderLeft: `2px solid ${isAdd ? "var(--ok)" : isDel ? "var(--err)" : "transparent"}`,
              fontFamily: "var(--font-mono)",
              fontSize: 12,
              lineHeight: "22px",
            }}
          >
            <span
              style={{
                width: 16,
                color: isAdd ? "var(--ok)" : isDel ? "var(--err)" : "var(--text-faint)",
                userSelect: "none",
              }}
            >
              {isAdd ? "+" : isDel ? "−" : " "}
            </span>
            <span style={{ color: "var(--text-dim)", whiteSpace: "pre-wrap", wordBreak: "break-all" }}>
              {line.text || " "}
            </span>
          </div>
        );
      })}
    </div>
  );
}

const TEXTAREA_STYLE: React.CSSProperties = {
  background: "var(--bg-2)",
  border: "1px solid var(--border)",
  borderRadius: 6,
  padding: "8px 10px",
  color: "var(--text)",
  fontSize: 12,
  fontFamily: "var(--font-mono)",
  resize: "vertical",
};

const INPUT_STYLE: React.CSSProperties = {
  background: "var(--bg-2)",
  border: "1px solid var(--border)",
  borderRadius: 6,
  padding: "6px 10px",
  color: "var(--text)",
  fontSize: 13,
};

const LABEL_STYLE: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 4,
  fontSize: 13,
};

export default async function PromptsPage({ params, searchParams }: Props) {
  const { org, project } = await params;
  const qp = await searchParams;

  if (!(await hasAuthToken())) return <AuthRequiredPanel layout="main" />;

  const resolved = await resolveProject(org, project);
  const promptsRes = await getPrompts(resolved.project_id);
  const prompts = promptsRes.data;

  const versionsByPrompt = new Map(
    await Promise.all(
      prompts.map(async (p) => [p.id, (await getPromptVersions(p.id)).data] as const),
    ),
  );
  const usageByPrompt = new Map<string, number>(
    await Promise.all(
      prompts.map(async (p) => {
        try {
          const usage = await getPromptUsage(p.id, 1);
          return [p.id, usage.usage_count] as const;
        } catch {
          return [p.id, 0] as const;
        }
      }),
    ),
  );

  const selectedId = qp.prompt ?? prompts[0]?.id;
  const selected = prompts.find((p) => p.id === selectedId) ?? prompts[0];
  const selectedVersions = selected ? (versionsByPrompt.get(selected.id) ?? []) : [];
  const latest = selectedVersions[selectedVersions.length - 1] ?? null;
  const previous = selectedVersions[selectedVersions.length - 2] ?? null;

  const base = `/o/${org}/p/${project}/prompts`;

  const totalPrompts = prompts.length;
  const totalVersions = Array.from(versionsByPrompt.values()).reduce(
    (acc, list) => acc + list.length,
    0,
  );
  const latestActivity = (() => {
    let mostRecent: string | null = null;
    for (const p of prompts) {
      if (!mostRecent || Date.parse(p.created_at) > Date.parse(mostRecent)) {
        mostRecent = p.created_at;
      }
      const versions = versionsByPrompt.get(p.id) ?? [];
      for (const v of versions) {
        if (!mostRecent || Date.parse(v.created_at) > Date.parse(mostRecent)) {
          mostRecent = v.created_at;
        }
      }
    }
    return mostRecent;
  })();

  return (
    <div className="page">
      {/* Header */}
      <div className="page-header">
        <div>
          <p className="page-header__eyebrow">Operação · Prompts</p>
          <h1 className="page-header__title">Prompts</h1>
          <p className="page-header__subtitle">
            Templates versionados. Cada versão é referenciada por traces e experimentos.
          </p>
        </div>
        <div className="row">
          <Link href="#prompt-create" className="btn btn--sm btn--primary">
            <Plus size={13} /> Novo prompt
          </Link>
        </div>
      </div>

      {/* Flash */}
      {qp.error && (
        <div style={{ padding: "10px 14px", background: "var(--err-bg)", border: "1px solid var(--err-border)", borderRadius: 6, color: "var(--err)", fontSize: 13, marginBottom: 12 }}>
          {qp.error}
        </div>
      )}
      {(qp.created || qp.versioned) && (
        <div style={{ padding: "10px 14px", background: "var(--ok-bg)", border: "1px solid var(--ok-border)", borderRadius: 6, color: "var(--ok)", fontSize: 13, marginBottom: 12 }}>
          {qp.created ? "Prompt criado com sucesso." : "Nova versão criada com sucesso."}
        </div>
      )}

      {/* Summary row — só dados reais do payload */}
      <section className="module-summary" aria-label="Resumo de prompts">
        <div className="summary-card">
          <p className="summary-card__label">Prompts</p>
          <div className="summary-card__value">{totalPrompts.toLocaleString("pt-BR")}</div>
          <div className="summary-card__hint">slugs versionados ativos</div>
        </div>
        <div className="summary-card">
          <p className="summary-card__label">Versões</p>
          <div className="summary-card__value">{totalVersions.toLocaleString("pt-BR")}</div>
          <div className="summary-card__hint">total publicado</div>
        </div>
        <div className="summary-card">
          <p className="summary-card__label">Última atividade</p>
          <div className="summary-card__value">
            {latestActivity ? relTime(latestActivity) : "—"}
          </div>
          <div className="summary-card__hint">prompt ou versão</div>
        </div>
      </section>

      {prompts.length === 0 ? (
        /* ── Empty state + create form ── */
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div className="card" style={{ padding: "40px 24px", textAlign: "center" }}>
            <p style={{ color: "var(--text-muted)", fontWeight: 600, marginBottom: 6 }}>Nenhum prompt ainda</p>
            <p style={{ color: "var(--text-faint)", fontSize: 13, maxWidth: 320, margin: "0 auto 16px" }}>
              Crie um prompt versionado antes de rodar experimentos controlados.
            </p>
            <ol style={{ textAlign: "left", display: "inline-block", fontSize: 13, color: "var(--text-muted)", lineHeight: "1.8" }}>
              <li>Crie um prompt com slug estável.</li>
              <li>Publique novas versões com changelog.</li>
              <li>Referencie versões em experimentos e traces.</li>
            </ol>
          </div>

          <div className="card">
            <div className="card__header">
              <h3 className="card__title">Criar prompt</h3>
            </div>
            <div className="card__body">
              <form action={createPromptAction} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                <input type="hidden" name="org" value={org} />
                <input type="hidden" name="project" value={project} />
                <input type="hidden" name="project_id" value={resolved.project_id} />
                <label style={LABEL_STYLE}>
                  <span style={{ color: "var(--text-muted)" }}>Slug</span>
                  <input name="slug" placeholder="support-answer-system" required style={INPUT_STYLE} />
                </label>
                <label style={LABEL_STYLE}>
                  <span style={{ color: "var(--text-muted)" }}>Descrição</span>
                  <input name="description" placeholder="Support answer system prompt" style={INPUT_STYLE} />
                </label>
                <label style={LABEL_STYLE}>
                  <span style={{ color: "var(--text-muted)" }}>Template</span>
                  <textarea name="template" rows={5} required defaultValue={"You are a helpful support assistant.\nUser: {{ user_message }}"} style={TEXTAREA_STYLE} />
                </label>
                <label style={LABEL_STYLE}>
                  <span style={{ color: "var(--text-muted)" }}>Variáveis JSON</span>
                  <textarea name="variables_json" rows={2} defaultValue={'{"user_message":{"type":"string","required":true}}'} style={TEXTAREA_STYLE} />
                </label>
                <label style={LABEL_STYLE}>
                  <span style={{ color: "var(--text-muted)" }}>Metadata JSON</span>
                  <textarea name="metadata_json" rows={2} defaultValue={'{"model_default":"openai/gpt-4o-mini","temperature_default":0.2}'} style={TEXTAREA_STYLE} />
                </label>
                <button type="submit" className="btn btn--primary" style={{ alignSelf: "flex-start" }}>
                  Criar prompt
                </button>
              </form>
            </div>
          </div>
        </div>
      ) : (
        /* ── Main layout: table + detail panel ── */
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          {/* Left: prompts table */}
          <div className="card">
            <div className="card__header">
              <h3 className="card__title">Prompts</h3>
              <span className="t__faint" style={{ fontSize: 11 }}>
                {prompts.length} prompt{prompts.length !== 1 ? "s" : ""}
              </span>
            </div>
            <div className="card__body" style={{ padding: 0 }}>
              <table className="t">
                <thead>
                  <tr>
                    <th>Nome</th>
                    <th>Versões</th>
                    <th>Usado por</th>
                    <th>Atualizado</th>
                  </tr>
                </thead>
                <tbody>
                  {prompts.map((p) => {
                    const isActive = p.id === selected?.id;
                    return (
                      <tr
                        key={p.id}
                        style={isActive ? { background: "var(--accent-bg)" } : undefined}
                      >
                        <td>
                          <Link
                            href={`${base}?prompt=${p.id}`}
                            style={{ textDecoration: "none", display: "flex", flexDirection: "column", gap: 2 }}
                          >
                            <span className="t__name">{p.slug}</span>
                            {p.description && (
                              <span style={{ fontSize: 11, color: "var(--text-faint)" }}>
                                {p.description}
                              </span>
                            )}
                          </Link>
                        </td>
                        <td>
                          <span
                            className="mono"
                            style={{
                              fontSize: 12,
                              color: isActive ? "var(--accent)" : "var(--text-dim)",
                              fontWeight: isActive ? 600 : 500,
                            }}
                          >
                            v{p.current_version}
                          </span>
                        </td>
                        <td>
                          <span className="mono t__muted" style={{ fontSize: 12 }}>
                            {(usageByPrompt.get(p.id) ?? 0).toLocaleString("pt-BR")} traces
                          </span>
                        </td>
                        <td className="t__muted" style={{ fontSize: 12 }}>
                          {relTime(p.created_at)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Right: diff / version detail */}
          {selected && (
            <div className="card">
              <div className="card__header">
                <div>
                  <h3 className="card__title">{selected.slug}</h3>
                  <div className="card__subtitle">
                    v{selected.current_version}
                    {previous ? ` vs v${previous.version}` : " · versão inicial"}
                  </div>
                </div>
                <div className="row" style={{ gap: 6 }}>
                  {previous && (
                    <span className="badge badge--ok">
                      <span className="badge__dot" />
                      atual
                    </span>
                  )}
                  <Link href="#prompt-version" className="btn btn--sm">
                    <GitBranch size={13} /> Nova versão
                  </Link>
                </div>
              </div>
              <div className="card__body" style={{ padding: 0, maxHeight: 400, overflow: "auto" }}>
                {latest ? (
                  <DiffView current={latest} previous={previous} />
                ) : (
                  <div style={{ padding: 24, color: "var(--text-faint)", fontSize: 13 }}>
                    Nenhuma versão encontrada.
                  </div>
                )}
              </div>

              {/* Version history */}
              <div style={{ borderTop: "1px solid var(--border-subtle)" }}>
                <div style={{ padding: "10px 16px 4px", fontSize: 11, color: "var(--text-faint)", fontWeight: 600, letterSpacing: "0.06em", textTransform: "uppercase" }}>
                  Versões
                </div>
                {selectedVersions.slice().reverse().map((v) => (
                  <div
                    key={v.id}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 10,
                      padding: "8px 16px",
                      borderTop: "1px solid var(--border-subtle)",
                    }}
                  >
                    <span
                      className="mono"
                      style={{
                        fontSize: 12,
                        color: v.version === selected.current_version ? "var(--accent)" : "var(--text-dim)",
                        fontWeight: v.version === selected.current_version ? 600 : 500,
                        minWidth: 28,
                      }}
                    >
                      v{v.version}
                    </span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 12, color: "var(--text-dim)" }}>
                        {relTime(v.created_at)}
                      </div>
                      <div style={{ fontSize: 11, color: "var(--text-faint)", fontFamily: "var(--font-mono)" }}>
                        {v.created_by}
                      </div>
                    </div>
                    {v.version === selected.current_version && (
                      <span className="badge badge--ok">
                        <span className="badge__dot" /> ativa
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Create new version (collapsible) — only when prompts exist */}
      {prompts.length > 0 && (
        <details
          id="prompt-create"
          style={{
            background: "var(--surface-1)",
            border: "1px solid var(--border)",
            borderRadius: 8,
            marginTop: 12,
          }}
        >
          <summary style={{ padding: "12px 16px", cursor: "pointer", fontSize: 13, fontWeight: 500, color: "var(--text-dim)", listStyle: "none" }}>
            <Plus size={13} style={{ display: "inline", marginRight: 6 }} />
            Criar novo prompt
          </summary>
          <div style={{ padding: "0 16px 20px" }}>
            <form action={createPromptAction} style={{ display: "flex", flexDirection: "column", gap: 12, marginTop: 12 }}>
              <input type="hidden" name="org" value={org} />
              <input type="hidden" name="project" value={project} />
              <input type="hidden" name="project_id" value={resolved.project_id} />
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                <label style={LABEL_STYLE}>
                  <span style={{ color: "var(--text-muted)" }}>Slug</span>
                  <input name="slug" placeholder="support-answer-system" required style={INPUT_STYLE} />
                </label>
                <label style={LABEL_STYLE}>
                  <span style={{ color: "var(--text-muted)" }}>Descrição</span>
                  <input name="description" placeholder="Support answer system prompt" style={INPUT_STYLE} />
                </label>
              </div>
              <label style={LABEL_STYLE}>
                <span style={{ color: "var(--text-muted)" }}>Template</span>
                <textarea name="template" rows={4} required defaultValue={"You are a helpful support assistant.\nUser: {{ user_message }}"} style={TEXTAREA_STYLE} />
              </label>
              <label style={LABEL_STYLE}>
                <span style={{ color: "var(--text-muted)" }}>Variáveis JSON</span>
                <textarea name="variables_json" rows={2} defaultValue={'{"user_message":{"type":"string","required":true}}'} style={TEXTAREA_STYLE} />
              </label>
              <label style={LABEL_STYLE}>
                <span style={{ color: "var(--text-muted)" }}>Metadata JSON</span>
                <textarea name="metadata_json" rows={2} defaultValue={'{"model_default":"openai/gpt-4o-mini","temperature_default":0.2}'} style={TEXTAREA_STYLE} />
              </label>
              <button type="submit" className="btn btn--primary" style={{ alignSelf: "flex-start" }}>
                Criar prompt
              </button>
            </form>
          </div>
        </details>
      )}

      {/* Add version to selected prompt */}
      {selected && selectedVersions.length > 0 && (
        <details
          id="prompt-version"
          style={{
            background: "var(--surface-1)",
            border: "1px solid var(--border)",
            borderRadius: 8,
            marginTop: 8,
          }}
        >
          <summary style={{ padding: "12px 16px", cursor: "pointer", fontSize: 13, fontWeight: 500, color: "var(--text-dim)", listStyle: "none" }}>
            <GitBranch size={13} style={{ display: "inline", marginRight: 6 }} />
            Nova versão — {selected.slug}
          </summary>
          <div style={{ padding: "0 16px 20px" }}>
            <form action={createPromptVersionAction} style={{ display: "flex", flexDirection: "column", gap: 12, marginTop: 12 }}>
              <input type="hidden" name="org" value={org} />
              <input type="hidden" name="project" value={project} />
              <input type="hidden" name="prompt_id" value={selected.id} />
              <label style={LABEL_STYLE}>
                <span style={{ color: "var(--text-muted)" }}>Template</span>
                <textarea name="template" rows={6} required defaultValue={latest?.template ?? ""} style={TEXTAREA_STYLE} />
              </label>
              <label style={LABEL_STYLE}>
                <span style={{ color: "var(--text-muted)" }}>Variáveis JSON</span>
                <textarea name="variables_json" rows={3} defaultValue={JSON.stringify(latest?.variables ?? {}, null, 2)} style={TEXTAREA_STYLE} />
              </label>
              <label style={LABEL_STYLE}>
                <span style={{ color: "var(--text-muted)" }}>Metadata JSON</span>
                <textarea name="metadata_json" rows={3} defaultValue={JSON.stringify(latest?.metadata ?? {}, null, 2)} style={TEXTAREA_STYLE} />
              </label>
              <button type="submit" className="btn btn--primary" style={{ alignSelf: "flex-start" }}>
                Publicar versão
              </button>
            </form>
          </div>
        </details>
      )}
    </div>
  );
}
