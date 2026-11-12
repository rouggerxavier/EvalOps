"use server";
import { redirect } from "next/navigation";
import { getSession } from "@/lib/auth";
import { resolveProject, taskRead, taskWrite, taskPatch } from "@/lib/api";
import { sanitizeApiError } from "@/lib/safe-error";
import type { CuratedCase } from "@/lib/investigation-types";

export async function saveCase(_previous: { error?: string }, form: FormData): Promise<{ error?: string }> {
  const org = String(form.get("org"));
  const project = String(form.get("project"));
  const dataset = String(form.get("dataset"));
  try {
    if (!(await getSession())) throw new Error("Autentique-se para editar casos.");
    const resolved = await resolveProject(org, project);
    const parent = await taskRead<{ project_id: string }>(`/datasets/${encodeURIComponent(dataset)}`);
    if (parent.project_id !== resolved.project_id) throw new Error("Dataset não pertence ao projeto.");
    const id = String(form.get("id") ?? "");
    const operation = String(form.get("operation"));
    if (!/^[a-f0-9-]{36}$/.test(operation)) throw new Error("Operação inválida.");
    const caseData = { sample_id: String(form.get("sample_id")), input: JSON.parse(String(form.get("input"))),
      expected_output: JSON.parse(String(form.get("expected_output"))), metadata: JSON.parse(String(form.get("metadata"))), reference_status: String(form.get("reference_status") ?? "draft") };
    if (id) {
      await taskPatch<CuratedCase>(`/datasets/${encodeURIComponent(dataset)}/cases/${encodeURIComponent(id)}`, {
        case: caseData, review_reason: String(form.get("review_reason") ?? "") || null,
      }, Number(form.get("revision")), operation);
    } else {
      const refs = String(form.get("source_refs") ?? "").split("\n").map(ref => ref.trim()).filter(Boolean);
      caseData.reference_status = "draft";
      await taskWrite<CuratedCase>(`/datasets/${encodeURIComponent(dataset)}/cases`, {
        environment: String(form.get("environment")), case: caseData, source_refs: refs,
      }, operation);
    }
  } catch (error) {
    const text = error instanceof Error ? error.message : "Não foi possível salvar o caso.";
    return { error: text.includes("409") ? "Caso alterado por outra operação. Recarregue para conferir a revisão atual." : sanitizeApiError(text) };
  }
  redirect(`/o/${org}/p/${project}/datasets/${dataset}/cases`);
}

export async function classifyDataset(_previous: { error?: string }, form: FormData): Promise<{ error?: string }> {
  const org = String(form.get("org"));
  const project = String(form.get("project"));
  const dataset = String(form.get("dataset"));
  try {
    if (!(await getSession())) throw new Error("Autentique-se para classificar a origem.");
    const resolved = await resolveProject(org, project);
    const parent = await taskRead<{ project_id: string }>(`/datasets/${encodeURIComponent(dataset)}`);
    if (parent.project_id !== resolved.project_id) throw new Error("Dataset não pertence ao projeto.");
    await taskWrite(`/task-resources/dataset/${encodeURIComponent(dataset)}/classify`, { environment: String(form.get("environment")) }, String(form.get("operation")));
  } catch (error) {
    return { error: sanitizeApiError(error instanceof Error ? error.message : "Não foi possível classificar.") };
  }
  const trace = String(form.get("trace") ?? "");
  redirect(`/o/${org}/p/${project}/datasets/${dataset}/cases${trace ? `?trace=${encodeURIComponent(trace)}` : ""}`);
}
