"use server";
import { redirect } from "next/navigation";
import { getSession } from "@/lib/auth";
import { resolveProject, taskRead, taskWrite, taskPatch } from "@/lib/api";
import { sanitizeApiError } from "@/lib/safe-error";
import type { Investigation } from "@/lib/investigation-types";

export async function saveInvestigation(_previous: { error?: string }, form: FormData): Promise<{ error?: string }> {
  const org = String(form.get("org"));
  const project = String(form.get("project"));
  let id = String(form.get("id") ?? "");
  try {
    if (!(await getSession())) throw new Error("Autentique-se para editar.");
    const resolved = await resolveProject(org, project);
    const lines = (key: string) => String(form.get(key) ?? "").split("\n").map(line => line.trim()).filter(Boolean);
    const state = { title: String(form.get("title")), status: String(form.get("status")), summary: String(form.get("summary") ?? ""),
      hypotheses: lines("hypotheses"), evidence_refs: lines("evidence_refs"), run_ids: lines("run_ids"), next_steps: lines("next_steps"), decision: String(form.get("decision") ?? "") || null };
    const operation = String(form.get("operation"));
    if (!/^[a-f0-9-]{36}$/.test(operation)) throw new Error("Operação inválida.");
    if (id) {
      const current = await taskRead<Investigation>(`/investigations/${encodeURIComponent(id)}`);
      if (current.project_id !== resolved.project_id) throw new Error("Investigação não pertence ao projeto.");
      const result = await taskPatch<Investigation>(`/investigations/${encodeURIComponent(id)}`, { state }, Number(form.get("revision")), operation);
      id = result.id;
    } else {
      const result = await taskWrite<Investigation>(`/projects/${resolved.project_id}/investigations`, { state, environment: String(form.get("environment")) }, operation);
      id = result.id;
    }
  } catch (error) {
    const text = error instanceof Error ? error.message : "Não foi possível salvar.";
    return { error: text.includes("409") ? "Outra revisão foi salva. Recarregue a investigação e compare o histórico antes de editar." : sanitizeApiError(text) };
  }
  redirect(`/o/${org}/p/${project}/evaluations/investigations/${id}`);
}
