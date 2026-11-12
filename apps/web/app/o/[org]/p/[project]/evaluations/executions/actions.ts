"use server";
import { redirect } from "next/navigation";
import { getSession } from "@/lib/auth";
import { resolveProject, taskWrite } from "@/lib/api";
import { sanitizeApiError } from "@/lib/safe-error";
export async function importExecution(_previous: { error?: string }, form: FormData): Promise<{ error?: string }> {
  const org = String(form.get("org"));
  const project = String(form.get("project"));
  let id: string;
  try {
    if (!(await getSession())) throw new Error("Autentique-se para importar evidências.");
    const resolved = await resolveProject(org, project);
    const operation = String(form.get("operation"));
    if (!/^[a-f0-9-]{36}$/.test(operation)) throw new Error("Operação inválida.");
    const content = JSON.parse(String(form.get("capture")));
    const result = await taskWrite<{ id: string }>(`/projects/${resolved.project_id}/execution-imports`, content, operation);
    id = result.id;
  } catch (error) {
    return { error: sanitizeApiError(error instanceof Error ? error.message : "Falha ao importar evidência.") };
  }
  redirect(`/o/${org}/p/${project}/evaluations/executions/${id}`);
}
