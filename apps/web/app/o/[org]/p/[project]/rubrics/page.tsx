import { ChevronLeft, GitBranch, Plus, Target } from "lucide-react";
import Link from "next/link";

import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { createRubricAction, createRubricVersionAction } from "@/lib/actions";
import { getRubrics, getRubricVersions, hasAuthToken, resolveProject } from "@/lib/api";
import type { RubricVersion } from "@/lib/types";

type Props = {
  params: Promise<{ org: string; project: string }>;
  searchParams: Promise<{ rubric?: string; error?: string; created?: string; versioned?: string }>;
};

const DEFAULT_YAML = `slug: answer-quality
name: Answer Quality
description: Check if the answer is acceptable
threshold: 0.7
aggregate: weighted_mean
evaluators:
  - id: length_check
    type: length_bounds
    weight: 1.0
    config:
      target: trace.output.assistant_message
      unit: chars
      min: 20
      max: 800`;

function YamlBlock({ code }: { code: string }) {
  const lines = code.split("\n");
  return (
    <div style={{ overflowX: "auto" }}>
      <pre
        style={{
          margin: 0,
          fontFamily: "var(--font-mono)",
          fontSize: 12,
          lineHeight: "20px",
          color: "var(--text-dim)",
          minWidth: "max-content",
        }}
      >
        {lines.map((line, i) => (
          <div key={i} style={{ display: "flex" }}>
            <span
              style={{
                display: "inline-block",
                minWidth: 36,
                paddingLeft: 12,
                paddingRight: 10,
                textAlign: "right",
                color: "var(--text-faint)",
                userSelect: "none",
                borderRight: "1px solid var(--border-subtle)",
                flexShrink: 0,
              }}
            >
              {i + 1}
            </span>
            <span style={{ paddingLeft: 14, whiteSpace: "pre" }}>{line || " "}</span>
          </div>
        ))}
      </pre>
    </div>
  );
}

function VersionsList({ versions, currentVersion }: { versions: RubricVersion[]; currentVersion: number }) {
  const formatDate = (s: string) =>
    new Date(s).toLocaleDateString("pt-BR", { day: "2-digit", month: "short", year: "numeric" });

  return (
    <div className="evo-card__body" style={{ padding: "4px 0" }}>
      {versions.length === 0 ? (
        <div style={{ padding: "12px 20px", color: "var(--text-faint)", fontSize: 13 }}>Nenhuma versão.</div>
      ) : (
        [...versions].reverse().map((v, i) => {
          const isLatest = v.version === currentVersion;
          return (
            <div
              key={v.id}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                padding: "10px 20px",
                borderTop: i > 0 ? "1px solid var(--border-subtle)" : "none",
              }}
            >
              <span
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: 12,
                  color: isLatest ? "var(--accent)" : "var(--text-dim)",
                  fontWeight: isLatest ? 600 : 500,
                  minWidth: 28,
                }}
              >
                v{v.version}
              </span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 12, color: "var(--text-dim)" }}>{formatDate(v.created_at)}</div>
                <div
                  style={{
                    fontSize: 11,
                    color: "var(--text-faint)",
                    fontFamily: "var(--font-mono)",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {v.created_by}
                </div>
              </div>
              {isLatest && (
                <span
                  className="evo-badge evo-badge--ok"
                  style={{ fontSize: 10, padding: "2px 7px" }}
                >
                  ativa
                </span>
              )}
            </div>
          );
        })
      )}
    </div>
  );
}

const inputStyle = {
  background: "var(--bg-2)",
  border: "1px solid var(--border)",
  borderRadius: 6,
  padding: "6px 10px",
  color: "var(--text)",
  fontSize: 13,
  width: "100%",
} as const;

const labelStyle = {
  display: "flex",
  flexDirection: "column",
  gap: 4,
  fontSize: 13,
} as const;

export default async function RubricsPage({ params, searchParams }: Props) {
  const { org, project } = await params;
  const qp = await searchParams;

  if (!(await hasAuthToken())) {
    return <AuthRequiredPanel layout="main" />;
  }

  const resolved = await resolveProject(org, project);
  const { data: rubrics } = await getRubrics(resolved.project_id);

  const selectedId = qp.rubric ?? null;
  const selected = selectedId ? (rubrics.find((r) => r.id === selectedId) ?? null) : null;

  let versions: RubricVersion[] = [];
  if (selected) {
    versions = (await getRubricVersions(selected.id)).data;
  }

  const latestVersion = versions.length > 0 ? versions[versions.length - 1] : null;
  const evaluators = latestVersion?.parsed_spec?.evaluators ?? [];

  const baseUrl = `/o/${org}/p/${project}/rubrics`;

  const formatDate = (s: string) =>
    new Date(s).toLocaleDateString("pt-BR", { day: "2-digit", month: "short", year: "numeric" });

  return (
    <div className="evo-page">
      {/* Page Header */}
      <div className="evo-page-header">
        <div style={{ flex: 1, minWidth: 0 }}>
          <p className="evo-page-header__eyebrow">Operação · Rubrics</p>
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 2 }}>
            {selected && (
              <Link
                href={baseUrl}
                style={{
                  color: "var(--text-faint)",
                  display: "inline-flex",
                  alignItems: "center",
                  marginRight: 2,
                  textDecoration: "none",
                }}
              >
                <ChevronLeft size={15} />
              </Link>
            )}
            <h1 className="evo-page-header__title">{selected ? selected.slug : "Rubrics"}</h1>
          </div>
          <p className="evo-page-header__subtitle">
            {selected
              ? `Rubric · versão ${selected.current_version} · ${evaluators.length} avaliador${evaluators.length !== 1 ? "es" : ""}`
              : `${rubrics.length} rubric${rubrics.length !== 1 ? "s" : ""} · critérios de avaliação versionados em YAML`}
          </p>
        </div>
        <div className="evo-page-header__actions">
          {!selected && rubrics.length > 0 && (
            <span style={{ fontSize: 12, color: "var(--text-faint)" }}>
              Clique em uma rubrica para ver detalhes
            </span>
          )}
        </div>
      </div>

      {/* Flash messages */}
      {qp.error && (
        <div
          style={{
            background: "var(--err-bg)",
            border: "1px solid var(--err-border)",
            borderRadius: 6,
            padding: "10px 14px",
            fontSize: 13,
            color: "var(--err)",
            marginBottom: 12,
          }}
        >
          {qp.error}
        </div>
      )}
      {(qp.created || qp.versioned) && (
        <div
          style={{
            background: "var(--ok-bg)",
            border: "1px solid var(--ok-border)",
            borderRadius: 6,
            padding: "10px 14px",
            fontSize: 13,
            color: "var(--ok)",
            marginBottom: 12,
          }}
        >
          {qp.created ? "Rubrica criada com sucesso." : "Nova versão criada."}
        </div>
      )}

      {selected ? (
        /* ---- DETAIL VIEW ---- */
        <div style={{ display: "grid", gridTemplateColumns: "1fr 360px", gap: 12 }}>
          {/* Left: YAML code block */}
          <div className="evo-card">
            <div className="evo-card__header">
              <h3 className="evo-card__title">Definição</h3>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span className="evo-badge evo-badge--info">YAML</span>
                <span style={{ fontSize: 11, color: "var(--text-faint)" }}>
                  versão {latestVersion?.version ?? "—"}
                </span>
              </div>
            </div>
            <div
              className="evo-card__body"
              style={{ padding: 0, maxHeight: 520, overflowY: "auto" }}
            >
              {latestVersion ? (
                <YamlBlock code={latestVersion.yaml_source} />
              ) : (
                <div style={{ padding: 24, color: "var(--text-faint)", fontSize: 13 }}>
                  Nenhuma versão encontrada.
                </div>
              )}
            </div>
          </div>

          {/* Right: Versions + Evaluators + New version form */}
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div className="evo-card">
              <div className="evo-card__header">
                <h3 className="evo-card__title">Versões</h3>
                <span style={{ fontSize: 11, color: "var(--text-faint)" }}>
                  {versions.length} versão{versions.length !== 1 ? "ões" : ""}
                </span>
              </div>
              <VersionsList versions={versions} currentVersion={selected.current_version} />
            </div>

            {evaluators.length > 0 && (
              <div className="evo-card">
                <div className="evo-card__header">
                  <h3 className="evo-card__title">Avaliadores</h3>
                  <span style={{ fontSize: 11, color: "var(--text-faint)" }}>
                    {evaluators.length} ativo{evaluators.length !== 1 ? "s" : ""}
                  </span>
                </div>
                <div className="evo-card__body" style={{ padding: "4px 0" }}>
                  {evaluators.map((ev, i) => (
                    <div
                      key={ev.id}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 10,
                        padding: "10px 20px",
                        borderTop: i > 0 ? "1px solid var(--border-subtle)" : "none",
                      }}
                    >
                      <Target
                        size={14}
                        style={{ color: "var(--text-muted)", flexShrink: 0 }}
                      />
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 13, color: "var(--text-dim)" }}>{ev.id}</div>
                        <div
                          style={{
                            fontSize: 11,
                            color: "var(--text-faint)",
                            fontFamily: "var(--font-mono)",
                          }}
                        >
                          {ev.type}
                        </div>
                      </div>
                      {ev.weight != null && (
                        <span
                          style={{
                            fontSize: 11,
                            color: "var(--text-faint)",
                            fontFamily: "var(--font-mono)",
                          }}
                        >
                          ×{ev.weight}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Nova versão collapsible */}
            <details
              style={{
                background: "var(--surface-1)",
                border: "1px solid var(--border)",
                borderRadius: 8,
              }}
            >
              <summary
                style={{
                  padding: "12px 16px",
                  cursor: "pointer",
                  fontSize: 13,
                  fontWeight: 500,
                  color: "var(--text-dim)",
                  listStyle: "none",
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                }}
              >
                <GitBranch size={13} /> Nova versão — {selected.slug}
              </summary>
              <div style={{ padding: "0 16px 20px" }}>
                <form
                  action={createRubricVersionAction}
                  style={{ display: "flex", flexDirection: "column", gap: 12, marginTop: 12 }}
                >
                  <input type="hidden" name="org" value={org} />
                  <input type="hidden" name="project" value={project} />
                  <input type="hidden" name="rubric_id" value={selected.id} />
                  <label style={labelStyle}>
                    <span style={{ color: "var(--text-muted)" }}>YAML</span>
                    <textarea
                      name="yaml_source"
                      required
                      rows={12}
                      defaultValue={latestVersion?.yaml_source ?? ""}
                      style={{
                        ...inputStyle,
                        fontFamily: "var(--font-mono)",
                        fontSize: 12,
                        resize: "vertical",
                      }}
                    />
                  </label>
                  <div style={{ display: "flex", justifyContent: "flex-end" }}>
                    <button type="submit" className="evo-btn evo-btn--sm evo-btn--primary">
                      Criar versão
                    </button>
                  </div>
                </form>
              </div>
            </details>
          </div>
        </div>
      ) : rubrics.length === 0 ? (
        /* ---- EMPTY STATE ---- */
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div className="evo-card">
            <div className="evo-card__header">
              <h3 className="evo-card__title">Criar primeira rubrica</h3>
            </div>
            <div className="evo-card__body">
              <p
                style={{
                  fontSize: 13,
                  color: "var(--text-dim)",
                  marginBottom: 20,
                  lineHeight: 1.6,
                }}
              >
                Rubricas são critérios de avaliação escritos em YAML. Cada rubrica define
                avaliadores e um threshold de aprovação.
              </p>
              <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 24 }}>
                {[
                  "Defina slug, threshold e evaluators no YAML.",
                  "Crie a rubrica — versão v1 é gerada automaticamente.",
                  "Vincule a rubrica a uma Evaluation para pontuar traces.",
                ].map((step, i) => (
                  <div key={i} style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                    <span
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        justifyContent: "center",
                        width: 20,
                        height: 20,
                        borderRadius: "50%",
                        background: "var(--accent-bg)",
                        color: "var(--accent)",
                        fontSize: 11,
                        fontWeight: 600,
                        flexShrink: 0,
                        marginTop: 1,
                      }}
                    >
                      {i + 1}
                    </span>
                    <span style={{ fontSize: 13, color: "var(--text-dim)", lineHeight: 1.5 }}>
                      {step}
                    </span>
                  </div>
                ))}
              </div>
              <form
                action={createRubricAction}
                style={{ display: "flex", flexDirection: "column", gap: 12 }}
              >
                <input type="hidden" name="org" value={org} />
                <input type="hidden" name="project" value={project} />
                <input type="hidden" name="project_id" value={resolved.project_id} />
                <label style={labelStyle}>
                  <span style={{ color: "var(--text-muted)" }}>YAML da rubrica</span>
                  <textarea
                    name="yaml_source"
                    required
                    rows={12}
                    defaultValue={DEFAULT_YAML}
                    style={{
                      ...inputStyle,
                      fontFamily: "var(--font-mono)",
                      fontSize: 12,
                      resize: "vertical",
                    }}
                  />
                </label>
                <button type="submit" className="evo-btn evo-btn--sm evo-btn--primary">
                  Criar rubrica
                </button>
              </form>
            </div>
          </div>

          <div className="evo-card" style={{ background: "var(--bg-2)" }}>
            <div className="evo-card__header">
              <h3 className="evo-card__title" style={{ color: "var(--text-muted)" }}>
                Exemplo de rubrica
              </h3>
              <span className="evo-badge evo-badge--info">YAML</span>
            </div>
            <div className="evo-card__body" style={{ padding: 0 }}>
              <YamlBlock code={DEFAULT_YAML} />
            </div>
          </div>
        </div>
      ) : (
        /* ---- LIST VIEW ---- */
        <>
          <div className="evo-table-wrap">
            <table className="evo-table">
              <thead>
                <tr>
                  <th>Rubrica</th>
                  <th>Descrição</th>
                  <th>Versão</th>
                  <th>Threshold</th>
                  <th>Criada</th>
                  <th style={{ width: 32 }}></th>
                </tr>
              </thead>
              <tbody>
                {rubrics.map((r) => (
                  <tr key={r.id}>
                    <td>
                      <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                        <Link
                          href={`${baseUrl}?rubric=${r.id}`}
                          className="evo-table__name"
                          style={{ color: "var(--text)", textDecoration: "none" }}
                        >
                          {r.slug}
                        </Link>
                        <span
                          style={{
                            fontSize: 11,
                            color: "var(--text-faint)",
                            fontFamily: "var(--font-mono)",
                          }}
                        >
                          {r.id}
                        </span>
                      </div>
                    </td>
                    <td style={{ color: "var(--text-muted)", fontSize: 13 }}>
                      {r.description ?? (
                        <span style={{ color: "var(--text-faint)" }}>—</span>
                      )}
                    </td>
                    <td>
                      <span
                        style={{
                          fontFamily: "var(--font-mono)",
                          fontSize: 12,
                          color: "var(--accent)",
                          fontWeight: 600,
                        }}
                      >
                        v{r.current_version}
                      </span>
                    </td>
                    <td>
                      <span
                        style={{
                          fontFamily: "var(--font-mono)",
                          fontSize: 12,
                          color:
                            r.threshold >= 0.8
                              ? "var(--ok)"
                              : r.threshold >= 0.6
                              ? "var(--warn)"
                              : "var(--err)",
                        }}
                      >
                        {r.threshold.toFixed(2)}
                      </span>
                    </td>
                    <td className="evo-muted">{formatDate(r.created_at)}</td>
                    <td>
                      <Link
                        href={`${baseUrl}?rubric=${r.id}`}
                        style={{ color: "var(--text-faint)", display: "flex" }}
                      >
                        <svg
                          width={14}
                          height={14}
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth={2}
                        >
                          <polyline points="9 18 15 12 9 6" />
                        </svg>
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Create form */}
          <details
            style={{
              background: "var(--surface-1)",
              border: "1px solid var(--border)",
              borderRadius: 8,
              marginTop: 16,
            }}
          >
            <summary
              style={{
                padding: "12px 16px",
                cursor: "pointer",
                fontSize: 13,
                fontWeight: 500,
                color: "var(--text-dim)",
                listStyle: "none",
                display: "flex",
                alignItems: "center",
                gap: 8,
              }}
            >
              <Plus size={13} /> Criar nova rubrica
            </summary>
            <div style={{ padding: "0 16px 20px" }}>
              <form
                action={createRubricAction}
                style={{ display: "flex", flexDirection: "column", gap: 12, marginTop: 12 }}
              >
                <input type="hidden" name="org" value={org} />
                <input type="hidden" name="project" value={project} />
                <input type="hidden" name="project_id" value={resolved.project_id} />
                <label style={labelStyle}>
                  <span style={{ color: "var(--text-muted)" }}>YAML da rubrica</span>
                  <textarea
                    name="yaml_source"
                    required
                    rows={14}
                    defaultValue={DEFAULT_YAML}
                    style={{
                      ...inputStyle,
                      fontFamily: "var(--font-mono)",
                      fontSize: 12,
                      resize: "vertical",
                    }}
                  />
                </label>
                <div style={{ display: "flex", justifyContent: "flex-end" }}>
                  <button type="submit" className="evo-btn evo-btn--sm evo-btn--primary">
                    Criar rubrica
                  </button>
                </div>
              </form>
            </div>
          </details>
        </>
      )}
    </div>
  );
}
