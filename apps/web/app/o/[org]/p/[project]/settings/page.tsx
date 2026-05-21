import Link from "next/link";
import { AlertCircle, CheckCircle2, Cog, ExternalLink, Users } from "lucide-react";

import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { Copyable } from "@/components/ui/Copyable";
import { patchProjectAction } from "@/lib/actions";
import {
  getMembers,
  getProjects,
  hasAuthToken,
  resolveProject,
} from "@/lib/api";
import { formatRelativeTime } from "@/lib/format";
import { safeErrorMessage } from "@/lib/safe-error";
import type { Member, Project } from "@/lib/types";

type Props = {
  params: Promise<{ org: string; project: string }>;
  searchParams: Promise<{ updated?: string; error?: string }>;
};

export default async function SettingsPage({ params, searchParams }: Props) {
  const { org, project } = await params;
  const qp = await searchParams;

  if (!(await hasAuthToken())) return <AuthRequiredPanel layout="main" />;

  const resolved = await resolveProject(org, project);

  const [projectsRes, membersRes] = await Promise.all([
    getProjects(resolved.org_id).catch(() => ({ data: [] as Project[] })),
    getMembers(resolved.org_id).catch(() => ({ data: [] as Member[] })),
  ]);

  const projectRecord =
    projectsRes.data.find((p) => p.id === resolved.project_id) ?? null;
  const members = membersRes.data;
  const safeQueryError = qp.error ? safeErrorMessage(qp.error, "Falha ao salvar.") : null;
  const updated = qp.updated === "1";

  const billingHref = `/o/${org}/usage`;

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <div className="page-header__eyebrow">
            Workspace · {resolved.org_slug}
          </div>
          <h1 className="page-header__title" style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <Cog size={18} /> Settings
          </h1>
          <div className="page-header__subtitle">
            Projeto · membros · billing
          </div>
        </div>
      </header>

      {updated ? (
        <div className="attention" style={{ borderColor: "rgba(106,224,168,0.4)" }}>
          <div className="attention__icon"><CheckCircle2 size={14} /></div>
          <div>
            <div className="attention__title">Projeto atualizado</div>
            <div className="attention__desc">Alterações persistidas em /v1/projects.</div>
          </div>
        </div>
      ) : null}

      {safeQueryError ? (
        <div className="attention" style={{ borderColor: "rgba(255,99,99,0.4)" }}>
          <div className="attention__icon"><AlertCircle size={14} /></div>
          <div>
            <div className="attention__title">Falha</div>
            <div className="attention__desc">{safeQueryError}</div>
          </div>
        </div>
      ) : null}

      <section className="grid-detail">
        <Card
          title="General"
          subtitle="PATCH /v1/projects/{id}"
        >
          {projectRecord === null ? (
            <p className="muted" style={{ margin: 0, fontSize: 12 }}>
              Não foi possível carregar dados do projeto.
            </p>
          ) : (
            <form
              action={patchProjectAction}
              style={{ display: "flex", flexDirection: "column", gap: 12 }}
            >
              <input type="hidden" name="org" value={org} />
              <input type="hidden" name="project" value={project} />
              <input type="hidden" name="project_id" value={projectRecord.id} />

              <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <span style={{ fontSize: 11, color: "var(--fg-3)" }}>Nome</span>
                <input
                  className="filter-input"
                  name="name"
                  defaultValue={projectRecord.name}
                  required
                  style={{ height: 32, padding: "0 10px" }}
                />
              </label>

              <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <span style={{ fontSize: 11, color: "var(--fg-3)" }}>Descrição</span>
                <input
                  className="filter-input"
                  name="description"
                  defaultValue={projectRecord.description ?? ""}
                  placeholder="(opcional)"
                  style={{ height: 32, padding: "0 10px" }}
                />
              </label>

              <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <span style={{ fontSize: 11, color: "var(--fg-3)" }}>Environment padrão</span>
                <select
                  className="filter-select"
                  name="default_environment"
                  defaultValue={projectRecord.default_environment}
                >
                  <option value="dev">dev</option>
                  <option value="staging">staging</option>
                  <option value="prod">prod</option>
                </select>
              </label>

              <div className="row" style={{ gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                <span className="tag mono">{projectRecord.slug}</span>
                <Copyable value={projectRecord.id} display={`${projectRecord.id.slice(0, 18)}…`} />
                <span className="faint mono" style={{ fontSize: 11 }}>
                  criado {formatRelativeTime(projectRecord.created_at)}
                </span>
              </div>

              <button type="submit" className="btn btn--sm btn--primary" style={{ justifyContent: "center" }}>
                Salvar alterações
              </button>
            </form>
          )}
        </Card>

        <div className="col" style={{ gap: 16 }}>
          <Card
            title="Members"
            subtitle={`${members.length} membro${members.length === 1 ? "" : "s"} · GET /v1/organizations/{id}/members`}
            flush
          >
            {members.length === 0 ? (
              <div className="t__empty">Sem memberships na organização.</div>
            ) : (
              <div className="table-wrap">
                <table className="t">
                  <thead>
                    <tr>
                      <th>
                        <span className="row" style={{ gap: 6, alignItems: "center" }}>
                          <Users size={11} /> Usuário
                        </span>
                      </th>
                      <th>Email</th>
                      <th>Role</th>
                      <th>Entrou</th>
                    </tr>
                  </thead>
                  <tbody>
                    {members.map((m) => (
                      <tr key={m.user_id}>
                        <td className="t__name">{m.name || "—"}</td>
                        <td className="t__mono">{m.email}</td>
                        <td>
                          <Badge variant={m.role === "owner" ? "info" : "ok"}>{m.role}</Badge>
                        </td>
                        <td className="t__muted">{formatRelativeTime(m.joined_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          <Card title="Billing" subtitle="usage + subscription">
            <p className="muted" style={{ margin: 0, marginBottom: 10, fontSize: 12 }}>
              Limites do plano e uso mensal vivem no painel da organização.
            </p>
            <Link className="btn btn--sm btn--ghost" href={billingHref}>
              <ExternalLink size={12} /> Abrir Usage · {resolved.org_slug}
            </Link>
          </Card>

          <Card title="Ações reais" subtitle="endpoints que esta tela usa">
            <div className="endpoint-list">
              {[
                { method: "GET", path: "/projects?organization_id=", note: "ativo" },
                { method: "PATCH", path: "/projects/{id}", note: "ativo" },
                { method: "GET", path: "/organizations/{id}/members", note: "ativo" },
                { method: "GET", path: "/organizations/{id}/usage", note: "link → /usage" },
              ].map((ep) => (
                <div className="endpoint-row" key={ep.path}>
                  <span className={`endpoint-snippet__method method-${ep.method}`}>{ep.method}</span>
                  <span className="endpoint-row__path">{ep.path}</span>
                  <span className="endpoint-row__note">{ep.note}</span>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </section>
    </div>
  );
}
