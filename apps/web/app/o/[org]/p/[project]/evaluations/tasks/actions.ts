"use server";

import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { getSession } from "@/lib/auth";
import { resolveProject, taskWrite, taskRead } from "@/lib/api";
import { sanitizeApiError } from "@/lib/safe-error";

export async function importRegression(_previous: { error?: string }, form: FormData): Promise<{ error?: string }> {
  const org = String(form.get("org") ?? "");
  const project = String(form.get("project") ?? "");
  const path = `/o/${encodeURIComponent(org)}/p/${encodeURIComponent(project)}/evaluations/tasks`;
  let id: string;
  try {
    if (!(await getSession())) throw new Error("Autentique-se para importar.");
    const resolved = await resolveProject(org, project);
    const capabilities = await taskRead<{ permissions: string[] }>(`/projects/${resolved.project_id}/capabilities`);
    if (!capabilities.permissions.includes("write")) throw new Error("Sem permissão de escrita.");
    const environment = String(form.get("environment"));
    if (!["dev", "staging", "prod"].includes(environment)) throw new Error("Ambiente inválido.");
    const operation = String(form.get("operation"));
    if (!/^[a-f0-9-]{36}$/.test(operation)) throw new Error("Operação inválida.");
    const data = JSON.parse(String(form.get("rows")));
    const access = { environment };
    const existingSnapshot = String(form.get("snapshot_id") ?? "");
    let snapshot: { id: string };
    if (existingSnapshot) {
      snapshot = await taskRead<{ id: string; project_id: string }>(`/dataset-snapshots/${encodeURIComponent(existingSnapshot)}`);
      if ((snapshot as { project_id?: string }).project_id !== resolved.project_id) throw new Error("Snapshot não pertence ao projeto.");
    } else {
    const dataset = await taskWrite<{ id: string }>(`/projects/${resolved.project_id}/datasets`, {
      slug: String(form.get("slug")), task_type: "regression",
      task_schema: { task_type: "regression", target: { name: String(form.get("target")), unit: String(form.get("unit")) } }, access,
      items: data.items,
    }, `${operation}:dataset`);
    snapshot = await taskWrite<{ id: string }>(`/datasets/${dataset.id}/snapshots`, { environment }, `${operation}:snapshot`);
    }
    const existingModel = String(form.get("model_version_id") ?? "");
    const model = existingModel ? { id: existingModel } : await taskWrite<{ id: string }>(`/projects/${resolved.project_id}/model-versions`, {
      model: { name: String(form.get("model")), version_ref: String(form.get("version")) }, access,
    }, `${operation}:model`);
    const predictions = await taskWrite<{ id: string }>(`/projects/${resolved.project_id}/prediction-sets`, {
      snapshot_id: snapshot.id, model_version_id: model.id, environment, rows: data.rows,
    }, `${operation}:predictions`);
    const evaluation = await taskWrite<{ id: string }>(`/projects/${resolved.project_id}/task-evaluations`, {
      prediction_set_id: predictions.id, evaluator: { id: "regression.standard", version: "1", config: {} },
    }, `${operation}:evaluation`);
    id = evaluation.id;
    revalidatePath(path);
  } catch (error) {
    const message = sanitizeApiError(error instanceof Error ? error.message : "Falha ao importar regressão.");
    return { error: message };
  }
  redirect(`${path}/${encodeURIComponent(id)}`);
}

export async function compareRegression(_previous: { error?: string }, form: FormData): Promise<{ error?: string }> {
  const org = String(form.get("org"));
  const project = String(form.get("project"));
  const path = `/o/${encodeURIComponent(org)}/p/${encodeURIComponent(project)}/evaluations/tasks`;
  let experimentId: string;
  let runId: string;
  try {
    if (!(await getSession())) throw new Error("Autentique-se para comparar.");
    const resolved = await resolveProject(org, project);
    const baseline = await taskRead<import("@/lib/task-types").TaskEvaluation>(`/task-evaluations/${encodeURIComponent(String(form.get("baseline")))}`);
    const candidate = await taskRead<import("@/lib/task-types").TaskEvaluation>(`/task-evaluations/${encodeURIComponent(String(form.get("candidate")))}`);
    if (baseline.project_id !== resolved.project_id || candidate.project_id !== resolved.project_id) throw new Error("Avaliação não pertence ao projeto.");
    const left = await taskRead<{ model_version_id: string }>(`/prediction-sets/${baseline.prediction_set_id}`);
    const right = await taskRead<{ model_version_id: string }>(`/prediction-sets/${candidate.prediction_set_id}`);
    const snapshot = await taskRead<{ dataset_id: string }>(`/dataset-snapshots/${baseline.snapshot_id}`);
    const operation = String(form.get("operation"));
    if (!/^[a-f0-9-]{36}$/.test(operation)) throw new Error("Operação inválida.");
    const experiment = await taskWrite<{ id: string }>(`/projects/${resolved.project_id}/experiments`, {
      kind: "task_comparison", name: "Comparação offline", dataset_id: snapshot.dataset_id, snapshot_id: baseline.snapshot_id,
      environment: baseline.environment, variants: [{ name: "baseline", model_version_id: left.model_version_id }, { name: "candidate", model_version_id: right.model_version_id }],
    }, `${operation}:experiment`);
    const run = await taskWrite<{ run: { id: string } }>(`/experiments/${experiment.id}/comparisons`, {
      baseline_evaluation_id: baseline.id, candidate_evaluation_ids: [candidate.id],
    }, `${operation}:comparison`);
    experimentId = experiment.id;
    runId = run.run.id;
  } catch (error) {
    return { error: sanitizeApiError(error instanceof Error ? error.message : "Falha ao comparar.") };
  }
  redirect(`${path}/comparison?experiment=${encodeURIComponent(experimentId)}&comparison_run=${encodeURIComponent(runId)}`);
}
