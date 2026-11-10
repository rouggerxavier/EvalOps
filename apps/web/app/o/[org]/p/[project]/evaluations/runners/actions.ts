"use server";
import { revalidatePath } from "next/cache";
import { getSession } from "@/lib/auth";
import { resolveProject, taskRead, taskWrite, taskPut } from "@/lib/api";
import { sanitizeApiError } from "@/lib/safe-error";
export type ControlState = { error?: string; message?: string; key?: string; credential_id?: string };
export async function controlRunner(previous: ControlState, form: FormData): Promise<ControlState> {
  try {
    if (!(await getSession())) throw new Error("Autentique-se para gerenciar runners.");
    const org = String(form.get("org"));
    const project = String(form.get("project"));
    const resolved = await resolveProject(org, project);
    const capabilities = await taskRead<{ permissions: string[] }>(`/projects/${resolved.project_id}/capabilities`);
    if (!capabilities.permissions.includes("admin")) throw new Error("Sem permissão para esta ação.");
    const intent = String(form.get("intent"));
    const operation = String(form.get("operation"));
    if (!/^[a-f0-9-]{36}$/.test(operation)) throw new Error("Operação inválida.");
    const id = String(form.get("runner_id"));
    if (intent === "policy") {
      await taskPut(`/projects/${resolved.project_id}/execution-policy`, JSON.parse(String(form.get("policy"))), Number(form.get("revision")), operation);
    } else if (intent === "register") {
      await taskWrite(`/projects/${resolved.project_id}/runners`, { name: String(form.get("name")), environments: JSON.parse(String(form.get("environments"))), adapter_versions: JSON.parse(String(form.get("adapters"))), isolation: "client_managed" }, operation);
    } else {
      const runner = await taskRead<{ project_id: string }>(`/runners/${encodeURIComponent(id)}`);
      if (runner.project_id !== resolved.project_id) throw new Error("Runner não pertence ao projeto.");
      if (intent === "disable") {
        await taskWrite(`/runners/${encodeURIComponent(id)}/disable`, {}, operation);
      } else if (intent === "credential") {
        const result = await taskWrite<{ key: string; id: string }>(`/runners/${encodeURIComponent(id)}/credentials`, { expires_at: String(form.get("expires_at")) }, operation);
        return { key: result.key, credential_id: result.id, message: "Chave criada. Copie agora; ela não será exibida em consultas posteriores." };
      } else if (intent === "revoke") {
        const credential = String(form.get("credential_id"));
        await taskWrite(`/runners/${encodeURIComponent(id)}/credentials/${encodeURIComponent(credential)}/revoke`, {}, operation);
        return { message: "Credencial revogada." };
      } else throw new Error("Operação inválida.");
    }
    revalidatePath(`/o/${org}/p/${project}/evaluations/runners`);
    return { message: "Configuração salva." };
  } catch (error) {
    return { ...previous, error: sanitizeApiError(error instanceof Error ? error.message : "Falha ao salvar configuração.") };
  }
}
