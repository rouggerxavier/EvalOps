"use server";
import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { getSession } from "@/lib/auth";
import { resolveProject, taskRead, taskWrite } from "@/lib/api";
import { sanitizeApiError } from "@/lib/safe-error";
export async function planOperation(_previous: { error?: string }, form: FormData): Promise<{ error?: string }> {
  const org = String(form.get("org"));
  const project = String(form.get("project"));
  const base = `/o/${org}/p/${project}/evaluations/executions`;
  let destination = base;
  try {
    if (!(await getSession())) throw new Error("Autentique-se para gerenciar a execução.");
    const resolved = await resolveProject(org, project);
    const operation = String(form.get("operation"));
    if (!/^[a-f0-9-]{36}$/.test(operation)) throw new Error("Operação inválida.");
    const intent = String(form.get("intent"));
    if (intent === "plan") {
      const payload = JSON.parse(String(form.get("payload")));
      const plan = await taskWrite<{ id: string }>(`/projects/${resolved.project_id}/execution-plans`, payload, operation);
      destination = `${base}/plans/${plan.id}`;
    } else if (intent === "enqueue") {
      const id = String(form.get("id"));
      const plan = await taskRead<{ project_id: string }>(`/execution-plans/${encodeURIComponent(id)}`);
      if (plan.project_id !== resolved.project_id) throw new Error("Plano não pertence ao projeto.");
      const execution = await taskWrite<{ id: string }>(`/projects/${resolved.project_id}/executions`, { plan_id: id }, operation);
      destination = `${base}/${execution.id}`;
    } else if (intent === "cancel") {
      const id = String(form.get("id"));
      const execution = await taskRead<{ project_id: string }>(`/executions/${encodeURIComponent(id)}`);
      if (execution.project_id !== resolved.project_id) throw new Error("Execução não pertence ao projeto.");
      await taskWrite(`/executions/${encodeURIComponent(id)}/cancel`, {}, operation);
      revalidatePath(`${base}/${id}`);
      return {};
    } else throw new Error("Operação inválida.");
  } catch (error) {
    return { error: sanitizeApiError(error instanceof Error ? error.message : "Falha ao gerenciar a execução.") };
  }
  redirect(destination);
}
