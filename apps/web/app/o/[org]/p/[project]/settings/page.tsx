import { AlertCircle, CheckCircle2 } from "lucide-react";

import { QualityGateForm } from "@/components/QualityGateForm";
import { AuthRequiredPanel } from "@/components/AuthRequiredPanel";
import { Copyable } from "@/components/ui/Copyable";
import { createProjectAction, patchProjectAction } from "@/lib/actions";
import {
  getQualityGateConfig,
  getMembers,
  getOrganizationSubscription,
  getOrganizationUsage,
  getProjects,
  hasAuthToken,
  resolveProject,
} from "@/lib/api";
import { safeErrorMessage } from "@/lib/safe-error";
import type { Member, OrgSubscription, OrgUsage, Project } from "@/lib/types";

type Props = {
  params: Promise<{ org: string; project: string }>;
  searchParams: Promise<{ updated?: string; created?: string; error?: string; gate_saved?: string }>;
};

function usd(value: number): string {
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(value);
}

function relativePt(iso: string): string {
  const minutes = Math.round((Date.now() - Date.parse(iso)) / 60_000);
  if (minutes < 1) return "agora";
  if (minutes < 60) return `há ${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `há ${hours} h`;
  const days = Math.round(hours / 24);
  return days < 14 ? `há ${days} dias` : `há ${Math.round(days / 7)} semanas`;
}

function UsageMeter({ label, value, limit }: { label: string; value: number; limit: number }) {
  const percent = limit > 0 ? Math.max(0, Math.min(100, (value / limit) * 100)) : 0;
  const formatter = new Intl.NumberFormat("pt-BR");
  return (
    <div className="ops-progress">
      <div className="ops-progress__header">
        <span>{label}</span>
        <span>{formatter.format(value)} de {formatter.format(limit)}</span>
      </div>
      <div className="ops-progress__track" role="img" aria-label={`${label}: ${formatter.format(value)} de ${formatter.format(limit)}`}>
        <span className="ops-progress__fill" style={{ width: `${percent}%` }} />
      </div>
    </div>
  );
}

function PlanAndUsage({
  usage,
  usageError,
  subscription,
  subscriptionError,
}: {
  usage: OrgUsage | null;
  usageError: string | null;
  subscription: OrgSubscription | null;
  subscriptionError: string | null;
}) {
  return (
    <section className="card">
      <div className="card__header">
        <h2 className="card__title">Plano e uso</h2>
        <span className="t__muted">Neste mês</span>
      </div>
      {subscription && usage ? (
        <div className="ops-usage-list">
          <UsageMeter label="Traces" value={usage.traces_ingested} limit={subscription.plan.monthly_trace_limit} />
          <UsageMeter label="Spans" value={usage.spans_ingested} limit={subscription.plan.monthly_span_limit} />
          <UsageMeter label="Avaliações" value={usage.evaluations_run} limit={subscription.plan.monthly_eval_limit} />
          <UsageMeter label="Exports" value={usage.exports_created} limit={subscription.plan.monthly_export_limit} />
          <div className="ops-progress">
            <div className="ops-progress__header">
              <span>Orçamento do juiz</span>
              <span>Sem dados de gasto / {usd(subscription.plan.monthly_judge_budget_usd)}</span>
            </div>
            <p className="ops-note">Gasto do juiz: Sem dados. O consumo de experimentos não aparece nesta conta.</p>
          </div>
        </div>
      ) : (
        <p className="ops-empty" role="alert">
          {subscriptionError ? `Sem dados do plano: ${subscriptionError}` : subscription ? `Sem dados de uso: ${usageError ?? "erro desconhecido"}` : `Sem dados do plano: ${subscriptionError ?? "erro desconhecido"}`}
        </p>
      )}
    </section>
  );
}

function roleLabel(role: string): string {
  if (role === "owner") return "Admin";
  if (role === "member") return "Membro";
  return role || "Sem dados";
}

function Members({ members, error }: { members: Member[]; error: string | null }) {
  return (
    <section className="card">
      <div className="card__header"><h2 className="card__title">Membros</h2></div>
      {error ? (
        <p className="ops-empty" role="alert">Sem dados de membros: {error}</p>
      ) : (
        <div className="table-wrap">
          <table className="t">
            <thead><tr><th>Nome</th><th>Email</th><th>Papel</th><th className="t__num">Entrou</th></tr></thead>
            <tbody>
              {members.length === 0 ? (
                <tr><td className="empty-row" colSpan={4}>Sem dados de membros.</td></tr>
              ) : members.map((member) => (
                <tr key={member.user_id}>
                  <td className="t__name">{member.name || "Sem dados"}</td>
                  <td>{member.email || "Sem dados"}</td>
                  <td>{roleLabel(member.role)}</td>
                  <td className="t__num">{relativePt(member.joined_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {!error ? <p className="ops-note">A lista retorna até 50 membros por consulta. Total: Sem dados.</p> : null}
    </section>
  );
}

export default async function SettingsPage({ params, searchParams }: Props) {
  const { org, project } = await params;
  const qp = await searchParams;

  if (!(await hasAuthToken())) return <AuthRequiredPanel layout="main" />;

  const resolved = await resolveProject(org, project);
  const [projectsResult, membersResult, usageResult, subscriptionResult, gateConfig] = await Promise.all([
    getProjects(resolved.org_id)
      .then((result) => ({ data: result.data, error: null as string | null }))
      .catch((error) => ({ data: [] as Project[], error: safeErrorMessage(error, "Falha ao carregar projetos.") })),
    getMembers(resolved.org_id)
      .then((result) => ({
        data: result.data,
        error: null as string | null,
      }))
      .catch((error) => ({ data: [] as Member[], error: safeErrorMessage(error, "Falha ao carregar membros.") })),
    getOrganizationUsage(resolved.org_id)
      .then((usage) => ({ usage, error: null as string | null }))
      .catch((error) => ({ usage: null, error: safeErrorMessage(error, "Falha ao carregar uso.") })),
    getOrganizationSubscription(resolved.org_id)
      .then((subscription) => ({ subscription, error: null as string | null }))
      .catch((error) => ({ subscription: null, error: safeErrorMessage(error, "Falha ao carregar plano.") })),
    getQualityGateConfig(resolved.project_id).catch(() => null),
  ]);

  const projectRecord = projectsResult.data.find((item) => item.id === resolved.project_id) ?? null;
  const safeQueryError = qp.error ? safeErrorMessage(qp.error, "Falha ao salvar.") : null;

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1 className="page-header__title">Ajustes</h1>
          <p className="page-header__subtitle">Quality Gate, projeto, plano, membros e novos projetos da organização.</p>
        </div>
      </header>

      {qp.updated ? <p className="ops-note" role="status"><CheckCircle2 size={14} aria-hidden="true" /> Projeto atualizado.</p> : null}
      {qp.created ? <p className="ops-note" role="status"><CheckCircle2 size={14} aria-hidden="true" /> Projeto criado.</p> : null}
      {safeQueryError ? <p className="ops-note" role="alert"><AlertCircle size={14} aria-hidden="true" /> {safeQueryError}</p> : null}
      {projectsResult.error ? <p className="ops-note" role="alert">Sem dados de projeto: {projectsResult.error}</p> : null}

      {qp.gate_saved === "1" ? <p className="ops-note" role="status"><CheckCircle2 size={14} aria-hidden="true" /> Quality Gate salvo. Confira o resultado na visão geral.</p> : null}
      <QualityGateForm config={gateConfig} org={org} project={project} />

      <div className="grid-2-eq ops-settings-grid">
        <div className="ops-stack">
          <section className="card">
            <div className="card__header"><h2 className="card__title">Projeto</h2></div>
            {projectRecord ? (
              <form action={patchProjectAction} className="ops-form">
                <input type="hidden" name="org" value={org} />
                <input type="hidden" name="project" value={project} />
                <input type="hidden" name="project_id" value={projectRecord.id} />
                <label className="ops-form__field">
                  <span>Nome</span>
                  <input name="name" defaultValue={projectRecord.name} minLength={2} required />
                </label>
                <label className="ops-form__field">
                  <span>Ambiente padrão</span>
                  <select name="default_environment" defaultValue={projectRecord.default_environment}>
                    <option value="prod">Produção</option>
                    <option value="staging">Staging</option>
                    <option value="dev">Dev</option>
                  </select>
                </label>
                <label className="ops-form__field">
                  <span>Descrição</span>
                  <input name="description" defaultValue={projectRecord.description ?? ""} placeholder="Opcional" />
                </label>
                <button type="submit" className="btn btn--primary">Salvar</button>
                <details className="ops-inline">
                  <summary>Identificação do projeto</summary>
                  <div className="row">
                    <span className="tag mono">{projectRecord.slug}</span>
                    <Copyable value={projectRecord.id} display={`${projectRecord.id.slice(0, 18)}…`} />
                    <span className="t__muted">criado {relativePt(projectRecord.created_at)}</span>
                  </div>
                </details>
              </form>
            ) : (
              <p className="ops-empty">Sem dados do projeto atual.</p>
            )}
          </section>

          <section className="card">
            <div className="card__header"><h2 className="card__title">Novo projeto</h2></div>
            <form action={createProjectAction} className="ops-form ops-form__grid">
              <input type="hidden" name="org" value={org} />
              <input type="hidden" name="project" value={project} />
              <input type="hidden" name="organization_id" value={resolved.org_id} />
              <label className="ops-form__field">
                <span>Nome</span>
                <input name="name" placeholder="Support Bot" minLength={2} required />
              </label>
              <label className="ops-form__field">
                <span>Identificador</span>
                <input name="slug" placeholder="support-bot" pattern="[a-z0-9-]+" minLength={2} required />
              </label>
              <details className="ops-inline">
                <summary>Mais opções</summary>
                <label className="ops-form__field">
                  <span>Descrição</span>
                  <input name="description" placeholder="Opcional" />
                </label>
                <label className="ops-form__field">
                  <span>Ambiente padrão</span>
                  <select name="default_environment" defaultValue="prod">
                    <option value="prod">Produção</option>
                    <option value="staging">Staging</option>
                    <option value="dev">Dev</option>
                  </select>
                </label>
              </details>
              <button type="submit" className="btn btn--primary">Criar projeto</button>
            </form>
          </section>
        </div>

        <div className="ops-stack">
          <PlanAndUsage
            usage={usageResult.usage}
            usageError={usageResult.error}
            subscription={subscriptionResult.subscription}
            subscriptionError={subscriptionResult.error}
          />
          <Members members={membersResult.data} error={membersResult.error} />
        </div>
      </div>
    </div>
  );
}
