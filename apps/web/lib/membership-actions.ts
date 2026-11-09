"use server";

import { revalidatePath } from "next/cache";
import { getSession } from "./auth";
import { getInvitations, membershipRequest } from "./api";
import type { InvitationAcceptance, InvitationList, Project } from "./types";

export type MembershipState = { error?: string; success?: string; leave?: boolean; acceptance?: InvitationAcceptance; href?: string; invitations?: InvitationList };

function failure(error: unknown): MembershipState {
  const message = error instanceof Error ? error.message : "";
  if (message.startsWith("API 401")) return { error: "Entre com sua conta pessoal para continuar. Sua sessão pode ter expirado." };
  if (message.startsWith("API 403")) return { error: "Sua conta não tem permissão para esta ação. Atualize a página." };
  if (message.startsWith("API 404")) return { error: "Membro ou convite indisponível nesta organização. Atualize a lista." };
  if (message.includes("last_owner")) return { error: "A organização precisa manter um owner. Transfira a propriedade antes de continuar." };
  if (message.includes("already_member")) return { error: "Este email já pertence a um membro. Altere o papel na lista de membros." };
  if (message.includes("invitation_already_accepted")) return { error: "O convite já foi aceito. Para retirar o acesso, use a lista de membros." };
  if (message.startsWith("API 409")) return { error: "A organização mudou durante esta ação. Atualize a lista e confirme novamente." };
  if (message.startsWith("API 422")) return { error: "Confira o email e o papel selecionado." };
  if (message.startsWith("API 429")) return { error: "Muitos pedidos. Aguarde alguns minutos antes de emitir outro convite." };
  return { error: "Não foi possível confirmar o resultado. Confira a lista antes de tentar novamente; o envio pode ter começado." };
}

export async function manageMembershipAction(form: FormData): Promise<MembershipState> {
  const org = String(form.get("org") ?? "");
  const project = String(form.get("project") ?? "");
  const orgId = String(form.get("organization_id") ?? "");
  const target = String(form.get("target") ?? "");
  const operation = String(form.get("operation") ?? "");
  if (![org, project, orgId].every((value) => /^[a-zA-Z0-9_-]{1,255}$/.test(value))) return { error: "Organização inválida. Atualize a página." };
  const base = `/organizations/${encodeURIComponent(orgId)}`;
  try {
    const session = await getSession();
    if (!session) return failure(new Error("API 401"));
    if (operation === "invite") {
      const raw = String(form.get("email") ?? "");
      const email = raw.trim().toLowerCase();
      const role = form.get("role");
      if (/[\r\n]/.test(raw) || email.length > 320 || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email) || (role !== "member" && role !== "viewer")) return { error: "Confira o email e o papel selecionado." };
      await membershipRequest(`${base}/invitations`, "POST", { email, role });
    } else {
      if (!/^[a-zA-Z0-9_-]{1,255}$/.test(target)) return { error: "Selecione um membro ou convite válido." };
      if (operation === "revoke") await membershipRequest(`${base}/invitations/${target}/revoke`, "POST");
      else if (operation === "remove" && form.get("confirmed") === "yes") await membershipRequest(`${base}/members/${target}`, "DELETE");
      else if (operation === "transfer" && form.get("confirmed") === "yes") await membershipRequest(`${base}/ownership/transfer`, "POST", { user_id: target });
      else if (operation === "role" && (form.get("role") === "member" || form.get("role") === "viewer")) await membershipRequest(`${base}/members/${target}`, "PATCH", { role: form.get("role") });
      else return { error: "Confirme a ação e o papel selecionado." };
    }
    revalidatePath(`/o/${org}/p/${project}`, "layout");
    return { success: operation === "invite" ? "Convite solicitado. Acompanhe o estado na lista." : "Alteração concluída.", leave: operation === "remove" && target === session.user.id };
  } catch (error) { return failure(error); }
}

export async function loadInvitationsAction(orgId: string, cursor?: string): Promise<MembershipState> {
  if (!/^[a-zA-Z0-9_-]{1,255}$/.test(orgId)) return { error: "Organização inválida." };
  try { return { invitations: await getInvitations(orgId, cursor) }; } catch (error) { return failure(error); }
}

export async function acceptInvitationAction(form: FormData): Promise<MembershipState> {
  const token = String(form.get("token") ?? "");
  if (!/^[A-Za-z0-9_-]{43}$/.test(token)) return { error: "Este convite é inválido, expirou ou já foi usado. Peça um novo convite." };
  let acceptance: InvitationAcceptance;
  try { acceptance = await membershipRequest<InvitationAcceptance>("/invitations/accept", "POST", { token }); }
  catch (error) {
    if (error instanceof Error && error.message.startsWith("API 400")) return { error: "Este convite é inválido, expirou ou já foi usado. Peça um novo convite." };
    return failure(error);
  }
  revalidatePath("/app");
  if (!acceptance.permissions.includes("read")) return { acceptance };
  try {
    const projects = await membershipRequest<{ data: Project[] }>(`/projects?organization_id=${encodeURIComponent(acceptance.organization_id)}`);
    const project = projects.data[0];
    return { acceptance, href: project ? `/o/${encodeURIComponent(acceptance.organization_slug)}/p/${encodeURIComponent(project.slug)}` : undefined };
  } catch { return { acceptance, success: "Convite aceito. Não foi possível carregar os projetos agora. Acesse o app novamente mais tarde." }; }
}
