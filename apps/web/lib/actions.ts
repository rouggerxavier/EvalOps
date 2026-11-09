"use server";

import { cookies } from "next/headers";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { isRedirectError } from "next/dist/client/components/redirect-error";

import { setApiKeyFlash } from "@/lib/flash";
import { parseQualityGateForm } from "@/lib/quality-gate";
import { sanitizeApiError } from "@/lib/safe-error";
import { resolveEnvironment } from "@/lib/environment";
import { getSession } from "@/lib/auth";
import {
  bulkFlagTraces,
  buildDatasetFromTraces,
  compareTraces,
  createApiKey,
  createDataset,
  createExport,
  createDatasetItems,
  createExperiment,
  createPrompt,
  createProject,
  createPromptVersion,
  createTraceFeedback,
  createRubric,
  createRubricVersion,
  deleteApiKey,
  flagTrace,
  getTrace,
  hideTrace,
  markNotificationsRead,
  patchProject,
  putQualityGateConfig,
  putSamplingConfig,
  retrySamplingJob,
  resolveProject,
  rerunTrace,
  revokeApiKey,
  runExperiment,
  triggerEvaluation,
  triggerEvaluationBatch,
} from "@/lib/api";

function projectPath(org: string, project: string, section: string): string {
  return `/o/${org}/p/${project}/${section}`;
}

function redirectWithMessage(path: string, params: Record<string, string>): never {
  const search = new URLSearchParams(params);
  redirect(`${path}?${search.toString()}`);
}

function messageFromActionError(error: unknown, fallback: string): string {
  if (isRedirectError(error)) {
    throw error;
  }
  if (!(error instanceof Error)) return fallback;
  return sanitizeApiError(error.message);
}

function parseJsonObject(raw: string, fallback: Record<string, unknown> = {}): Record<string, unknown> {
  if (!raw.trim()) return fallback;
  const parsed = JSON.parse(raw);
  if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
    return parsed as Record<string, unknown>;
  }
  return fallback;
}

function traceIdsFromForm(formData: FormData): string[] {
  const repeated = formData.getAll("trace_ids").map(String).filter(Boolean);
  const commaSeparated = String(formData.get("trace_ids_csv") ?? "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
  return [...new Set([...repeated, ...commaSeparated])];
}

const ENV_COOKIE = "evalops_env";

export async function createApiKeyAction(formData: FormData): Promise<void> {
  const org = String(formData.get("org") ?? "");
  const project = String(formData.get("project") ?? "");
  const projectId = String(formData.get("project_id") ?? "");
  const name = String(formData.get("name") ?? "");
  const environment = String(formData.get("environment") ?? "prod") as "dev" | "staging" | "prod";
  const scopes = formData.getAll("scopes").map(String);
  const path = projectPath(org, project, "keys");

  let result: { key: string; prefix: string } | null = null;
  let errorMsg: string | null = null;
  try {
    result = await createApiKey(projectId, {
      name,
      environment,
      scopes: scopes.length > 0 ? scopes : ["ingest", "read"],
    });
    revalidatePath(path);
  } catch (error) {
    errorMsg = messageFromActionError(error, "Failed to create API key");
  }
  if (result) {
    await setApiKeyFlash({ key: result.key, prefix: result.prefix });
    redirectWithMessage(path, { created: "1" });
  } else {
    redirectWithMessage(path, { error: errorMsg ?? "Failed to create API key" });
  }
}

export async function revokeApiKeyAction(formData: FormData): Promise<void> {
  const org = String(formData.get("org") ?? "");
  const project = String(formData.get("project") ?? "");
  const projectId = String(formData.get("project_id") ?? "");
  const keyId = String(formData.get("key_id") ?? "");
  const path = projectPath(org, project, "keys");

  let errorMsg: string | null = null;
  try {
    await revokeApiKey(projectId, keyId);
    revalidatePath(path);
  } catch (error) {
    errorMsg = messageFromActionError(error, "Failed to revoke API key");
  }
  redirectWithMessage(path, errorMsg ? { error: errorMsg } : { revoked: "1" });
}

export async function deleteApiKeyAction(formData: FormData): Promise<void> {
  const org = String(formData.get("org") ?? "");
  const project = String(formData.get("project") ?? "");
  const projectId = String(formData.get("project_id") ?? "");
  const keyId = String(formData.get("key_id") ?? "");
  const path = projectPath(org, project, "keys");

  let errorMsg: string | null = null;
  try {
    await deleteApiKey(projectId, keyId);
    revalidatePath(path);
  } catch (error) {
    errorMsg = messageFromActionError(error, "Failed to delete API key");
  }
  redirectWithMessage(path, errorMsg ? { error: errorMsg } : { deleted: "1" });
}

export async function createRubricAction(formData: FormData): Promise<void> {
  const org = String(formData.get("org") ?? "");
  const project = String(formData.get("project") ?? "");
  const projectId = String(formData.get("project_id") ?? "");
  const yamlSource = String(formData.get("yaml_source") ?? "");
  const section = String(formData.get("redirect_section") ?? "rubrics");
  const path = projectPath(org, project, section);

  let errorMsg: string | null = null;
  let ignored: string[] = [];
  try {
    ignored = (await createRubric(projectId, yamlSource)).ignored_fields ?? [];
    revalidatePath(path);
  } catch (error) {
    errorMsg = messageFromActionError(error, "Failed to create rubric");
  }
  redirectWithMessage(
    path,
    errorMsg ? { error: errorMsg } : { created: "1", ...(ignored.length ? { ignored: ignored.join(",") } : {}) },
  );
}

export async function createRubricVersionAction(formData: FormData): Promise<void> {
  const org = String(formData.get("org") ?? "");
  const project = String(formData.get("project") ?? "");
  const rubricId = String(formData.get("rubric_id") ?? "");
  const yamlSource = String(formData.get("yaml_source") ?? "");
  const section = String(formData.get("redirect_section") ?? "rubrics");
  const path = projectPath(org, project, section);

  let errorMsg: string | null = null;
  let ignored: string[] = [];
  try {
    ignored = (await createRubricVersion(rubricId, yamlSource)).ignored_fields ?? [];
    revalidatePath(path);
  } catch (error) {
    errorMsg = messageFromActionError(error, "Failed to create rubric version");
  }
  redirectWithMessage(
    path,
    errorMsg ? { error: errorMsg } : { versioned: "1", ...(ignored.length ? { ignored: ignored.join(",") } : {}) },
  );
}

export async function triggerEvaluationAction(formData: FormData): Promise<void> {
  const org = String(formData.get("org") ?? "");
  const project = String(formData.get("project") ?? "");
  const traceId = String(formData.get("trace_id") ?? "");
  const rubricId = String(formData.get("rubric_id") ?? "");
  const rubricVersionRaw = String(formData.get("rubric_version") ?? "").trim();
  // From the trace page the result is one tab away: go there instead of to the list.
  const fromTrace = formData.get("return_to") === "trace";
  const path = projectPath(org, project, fromTrace ? `traces/${traceId}` : "evaluations");

  let errorMsg: string | null = null;
  try {
    await triggerEvaluation({
      trace_id: traceId,
      rubric_id: rubricId,
      rubric_version: rubricVersionRaw ? Number(rubricVersionRaw) : undefined,
      triggered_by: "dashboard",
    });
    revalidatePath(path);
  } catch (error) {
    errorMsg = messageFromActionError(error, "Failed to run evaluation");
  }
  if (fromTrace) redirectWithMessage(path, errorMsg ? { tab: "evaluations", error: errorMsg } : { tab: "evaluations" });
  redirectWithMessage(path, errorMsg ? { error: errorMsg } : { created: "1" });
}

export async function triggerEvaluationBatchAction(formData: FormData): Promise<void> {
  const org = String(formData.get("org") ?? "");
  const project = String(formData.get("project") ?? "");
  const projectId = String(formData.get("project_id") ?? "");
  const rubricId = String(formData.get("rubric_id") ?? "");
  const rubricVersionRaw = String(formData.get("rubric_version") ?? "").trim();
  const environment = String(formData.get("environment") ?? "").trim();
  const nameContains = String(formData.get("name_contains") ?? "").trim();
  const limitRaw = String(formData.get("limit") ?? "").trim();
  const path = projectPath(org, project, "rubrics");

  let errorMsg: string | null = null;
  let enqueued = 0;
  try {
    const result = await triggerEvaluationBatch(projectId, {
      rubric_id: rubricId,
      rubric_version: rubricVersionRaw ? Number(rubricVersionRaw) : undefined,
      environment: environment || undefined,
      name_contains: nameContains || undefined,
      limit: limitRaw ? Number(limitRaw) : undefined,
    });
    enqueued = result.enqueued;
    revalidatePath(path);
  } catch (error) {
    errorMsg =
      error instanceof Error && error.message.startsWith("API 503")
        ? "A fila de avaliação está fora do ar (o worker não está rodando). Nada foi enfileirado; tente de novo mais tarde."
        : messageFromActionError(error, "Falha ao enfileirar avaliações");
  }
  redirectWithMessage(
    path,
    errorMsg ? { rubric: rubricId, error: errorMsg } : { rubric: rubricId, batched: String(enqueued) },
  );
}

export async function triggerEvaluationFromOverviewAction(formData: FormData): Promise<void> {
  const org = String(formData.get("org") ?? "");
  const project = String(formData.get("project") ?? "");
  const traceId = String(formData.get("trace_id") ?? "");
  const rubricId = String(formData.get("rubric_id") ?? "");
  const rubricVersionRaw = String(formData.get("rubric_version") ?? "").trim();
  const path = `/o/${org}/p/${project}`;

  let errorMsg: string | null = null;
  try {
    await triggerEvaluation({
      trace_id: traceId,
      rubric_id: rubricId,
      rubric_version: rubricVersionRaw ? Number(rubricVersionRaw) : undefined,
      triggered_by: "dashboard",
    });
    revalidatePath(path);
  } catch (error) {
    errorMsg = messageFromActionError(error, "Failed to run evaluation");
  }
  redirectWithMessage(path, errorMsg ? { error: errorMsg } : { evaluation: "1" });
}

export async function publishRubricAction(formData: FormData): Promise<void> {
  const org = String(formData.get("org") ?? "");
  const project = String(formData.get("project") ?? "");
  const rubricId = String(formData.get("rubric_id") ?? "");
  const yamlSource = String(formData.get("yaml_source") ?? "");
  const section = String(formData.get("redirect_section") ?? "rubrics");
  const path = projectPath(org, project, section);

  let errorMsg: string | null = null;
  try {
    await createRubricVersion(rubricId, yamlSource);
    revalidatePath(path);
  } catch (error) {
    errorMsg = messageFromActionError(error, "Failed to publish rubric");
  }
  redirectWithMessage(path, errorMsg ? { error: errorMsg } : { published: "1" });
}

export async function createPromptAction(formData: FormData): Promise<void> {
  const org = String(formData.get("org") ?? "");
  const project = String(formData.get("project") ?? "");
  const projectId = String(formData.get("project_id") ?? "");
  const slug = String(formData.get("slug") ?? "");
  const description = String(formData.get("description") ?? "");
  const template = String(formData.get("template") ?? "");
  const variablesRaw = String(formData.get("variables_json") ?? "{}");
  const metadataRaw = String(formData.get("metadata_json") ?? "{}");
  const path = projectPath(org, project, "prompts");

  let errorMsg: string | null = null;
  try {
    await createPrompt(projectId, {
      slug,
      description: description || undefined,
      template,
      variables: JSON.parse(variablesRaw),
      metadata: JSON.parse(metadataRaw),
      changelog: "Created from dashboard",
    });
    revalidatePath(path);
  } catch (error) {
    errorMsg = messageFromActionError(error, "Failed to create prompt");
  }
  redirectWithMessage(path, errorMsg ? { error: errorMsg } : { created: "1" });
}

export async function createPromptVersionAction(formData: FormData): Promise<void> {
  const org = String(formData.get("org") ?? "");
  const project = String(formData.get("project") ?? "");
  const promptId = String(formData.get("prompt_id") ?? "");
  const template = String(formData.get("template") ?? "");
  const variablesRaw = String(formData.get("variables_json") ?? "{}");
  const metadataRaw = String(formData.get("metadata_json") ?? "{}");
  const path = projectPath(org, project, "prompts");

  let errorMsg: string | null = null;
  try {
    await createPromptVersion(promptId, {
      template,
      variables: JSON.parse(variablesRaw),
      metadata: JSON.parse(metadataRaw),
      changelog: "Updated from dashboard",
    });
    revalidatePath(path);
  } catch (error) {
    errorMsg = messageFromActionError(error, "Failed to create prompt version");
  }
  redirectWithMessage(path, errorMsg ? { error: errorMsg } : { versioned: "1" });
}

export async function createDatasetAction(formData: FormData): Promise<void> {
  const org = String(formData.get("org") ?? "");
  const project = String(formData.get("project") ?? "");
  const projectId = String(formData.get("project_id") ?? "");
  const slug = String(formData.get("slug") ?? "");
  const description = String(formData.get("description") ?? "");
  const source = String(formData.get("source") ?? "manual");
  const path = projectPath(org, project, "datasets");

  let errorMsg: string | null = null;
  try {
    await createDataset(projectId, {
      slug,
      description: description || undefined,
      source,
    });
    revalidatePath(path);
  } catch (error) {
    errorMsg = messageFromActionError(error, "Failed to create dataset");
  }
  redirectWithMessage(path, errorMsg ? { error: errorMsg } : { created: "1" });
}

export async function addDatasetItemAction(formData: FormData): Promise<void> {
  const org = String(formData.get("org") ?? "");
  const project = String(formData.get("project") ?? "");
  const datasetId = String(formData.get("dataset_id") ?? "");
  const inputRaw = String(formData.get("input_json") ?? "{}");
  const expectedRaw = String(formData.get("expected_output_json") ?? "{}");
  const metadataRaw = String(formData.get("metadata_json") ?? "{}");
  const path = projectPath(org, project, "datasets");

  let errorMsg: string | null = null;
  try {
    await createDatasetItems(datasetId, {
      items: [
        {
          input: JSON.parse(inputRaw),
          expected_output: expectedRaw.trim() ? JSON.parse(expectedRaw) : null,
          metadata: JSON.parse(metadataRaw),
        },
      ],
    });
    revalidatePath(path);
  } catch (error) {
    errorMsg = messageFromActionError(error, "Failed to add dataset item");
  }
  redirectWithMessage(path, errorMsg ? { error: errorMsg } : { items_added: "1" });
}

export async function buildDatasetFromTracesAction(formData: FormData): Promise<void> {
  const org = String(formData.get("org") ?? "");
  const project = String(formData.get("project") ?? "");
  const datasetId = String(formData.get("dataset_id") ?? "");
  const environment = String(formData.get("environment") ?? "");
  const status = String(formData.get("status") ?? "");
  const limitRaw = String(formData.get("limit") ?? "50");
  const path = projectPath(org, project, "datasets");

  let errorMsg: string | null = null;
  try {
    await buildDatasetFromTraces(datasetId, {
      environment: environment || undefined,
      status: status || undefined,
      limit: Number(limitRaw) || 50,
    });
    revalidatePath(path);
  } catch (error) {
    errorMsg = messageFromActionError(error, "Failed to build dataset from traces");
  }
  redirectWithMessage(path, errorMsg ? { error: errorMsg } : { built: "1" });
}

export async function createExperimentAction(formData: FormData): Promise<void> {
  const org = String(formData.get("org") ?? "");
  const project = String(formData.get("project") ?? "");
  const projectId = String(formData.get("project_id") ?? "");
  const name = String(formData.get("name") ?? "");
  const datasetId = String(formData.get("dataset_id") ?? "");
  const rubricId = String(formData.get("rubric_id") ?? "");
  const variantsRaw = String(formData.get("variants_json") ?? "[]");
  const passCriteriaRaw = String(formData.get("pass_criteria_json") ?? "{}");
  const baselineVariant = String(formData.get("baseline_variant") ?? "");
  const path = projectPath(org, project, "experiments");

  let errorMsg: string | null = null;
  try {
    await createExperiment(projectId, {
      name,
      dataset_id: datasetId,
      rubric_id: rubricId,
      variants: JSON.parse(variantsRaw),
      pass_criteria: JSON.parse(passCriteriaRaw),
      baseline_variant: baselineVariant || undefined,
    });
    revalidatePath(path);
  } catch (error) {
    errorMsg = messageFromActionError(error, "Failed to create experiment");
  }
  redirectWithMessage(path, errorMsg ? { error: errorMsg } : { created: "1" });
}

export async function runExperimentAction(formData: FormData): Promise<void> {
  const org = String(formData.get("org") ?? "");
  const project = String(formData.get("project") ?? "");
  const experimentId = String(formData.get("experiment_id") ?? "");
  const path = projectPath(org, project, "experiments");

  let result: { run_id: string } | null = null;
  let errorMsg: string | null = null;
  try {
    result = await runExperiment(experimentId, { triggered_by: "dashboard" });
    revalidatePath(path);
  } catch (error) {
    errorMsg = messageFromActionError(error, "Failed to run experiment");
  }
  if (result) {
    redirectWithMessage(path, { run: "1", run_id: result.run_id, experiment_id: experimentId });
  } else {
    redirectWithMessage(path, { error: errorMsg ?? "Failed to run experiment" });
  }
}

export async function createTraceFeedbackAction(formData: FormData): Promise<void> {
  const org = String(formData.get("org") ?? "");
  const project = String(formData.get("project") ?? "");
  const traceId = String(formData.get("trace_id") ?? "");
  const thumbs = String(formData.get("thumbs") ?? "");
  const comment = String(formData.get("comment") ?? "");
  const path = projectPath(org, project, `traces/${traceId}`);

  let errorMsg: string | null = null;
  try {
    await createTraceFeedback(traceId, {
      source: "dashboard",
      thumbs: thumbs === "up" || thumbs === "down" ? thumbs : undefined,
      comment: comment || undefined,
    });
    revalidatePath(path);
  } catch (error) {
    errorMsg = messageFromActionError(error, "Failed to create feedback");
  }
  redirectWithMessage(path, errorMsg ? { error: errorMsg } : { feedback: "1" });
}

export async function flagTraceAction(formData: FormData): Promise<void> {
  const org = String(formData.get("org") ?? "");
  const project = String(formData.get("project") ?? "");
  const traceId = String(formData.get("trace_id") ?? "");
  const reason = String(formData.get("reason") ?? "manual");
  const note = String(formData.get("note") ?? "");
  const path = projectPath(org, project, `traces/${traceId}`);

  let errorMsg: string | null = null;
  try {
    await flagTrace(traceId, { reason, note: note || undefined });
    revalidatePath(path);
    revalidatePath(projectPath(org, project, "traces"));
  } catch (error) {
    errorMsg = messageFromActionError(error, "Failed to flag trace");
  }
  redirectWithMessage(path, errorMsg ? { error: errorMsg } : { flagged: "1" });
}

export async function hideTraceAction(_previous: { error: string | null }, formData: FormData): Promise<{ error: string | null }> {
  const org = String(formData.get("org") ?? "");
  const project = String(formData.get("project") ?? "");
  const traceId = String(formData.get("trace_id") ?? "");
  if (![org, project, traceId].every((value) => /^[a-zA-Z0-9_-]{1,255}$/.test(value)) || traceId.length > 64) {
    return { error: "Trace inválido. Volte à lista e abra o trace novamente." };
  }
  const path = projectPath(org, project, "traces");
  const rawEnvironment = formData.get("environment");
  const environment = rawEnvironment === "" ? "" : typeof rawEnvironment === "string" ? resolveEnvironment(rawEnvironment) : undefined;
  try {
    const session = await getSession();
    if (!session) return { error: "Entre com sua conta pessoal para ocultar este trace." };
    const resolved = await resolveProject(org, project);
    const detail = await getTrace(traceId);
    if (detail.trace.project_id !== resolved.project_id) {
      return { error: "Trace indisponível neste projeto. Volte à lista e atualize a página." };
    }
    await hideTrace(traceId, session.token);
  } catch (error) {
    const status = error instanceof Error ? error.message.match(/^API (\d{3})(?:\b|:)/)?.[1] : undefined;
    if (status === "401") return { error: "Sua sessão expirou. Entre novamente para ocultar o trace." };
    if (status === "403") return { error: "Sua conta não tem permissão para ocultar este trace." };
    if (status === "404") return { error: "Trace indisponível. Ele pode já estar oculto. Volte à lista e atualize a página." };
    return { error: "Não foi possível ocultar o trace. Tente novamente." };
  }
  revalidatePath(path);
  revalidatePath(projectPath(org, project, `traces/${traceId}`));
  redirectWithMessage(path, environment === undefined ? {} : { environment });
}

export async function bulkFlagTracesAction(formData: FormData): Promise<void> {
  const org = String(formData.get("org") ?? "");
  const project = String(formData.get("project") ?? "");
  const reason = String(formData.get("reason") ?? "manual");
  const note = String(formData.get("note") ?? "");
  const path = projectPath(org, project, "traces");

  let errorMsg: string | null = null;
  try {
    const traceIds = traceIdsFromForm(formData);
    if (traceIds.length === 0) throw new Error("No traces selected");
    await bulkFlagTraces({ trace_ids: traceIds, reason, note: note || undefined });
    revalidatePath(path);
  } catch (error) {
    errorMsg = messageFromActionError(error, "Failed to flag traces");
  }
  redirectWithMessage(path, errorMsg ? { error: errorMsg } : { flagged: "1" });
}

export async function rerunTraceAction(formData: FormData): Promise<void> {
  const org = String(formData.get("org") ?? "");
  const project = String(formData.get("project") ?? "");
  const traceId = String(formData.get("trace_id") ?? "");
  const model = String(formData.get("model") ?? "");
  const variablesRaw = String(formData.get("variables_json") ?? "{}");
  const path = projectPath(org, project, `traces/${traceId}`);

  let result: { new_trace_id: string } | null = null;
  let errorMsg: string | null = null;
  try {
    result = await rerunTrace(traceId, {
      model: model || undefined,
      variables: parseJsonObject(variablesRaw),
    });
    revalidatePath(path);
    revalidatePath(projectPath(org, project, "traces"));
  } catch (error) {
    errorMsg = messageFromActionError(error, "Failed to rerun trace");
  }
  redirectWithMessage(
    path,
    result ? { rerun: "1", new_trace_id: result.new_trace_id } : { error: errorMsg ?? "Failed to rerun trace" },
  );
}

export async function compareTracesAction(formData: FormData): Promise<void> {
  const org = String(formData.get("org") ?? "");
  const project = String(formData.get("project") ?? "");
  const leftTraceId = String(formData.get("left_trace_id") ?? formData.get("trace_id") ?? "");
  const rightTraceId = String(formData.get("right_trace_id") ?? "");
  const sourcePath = projectPath(org, project, leftTraceId ? `traces/${leftTraceId}` : "traces");
  const comparePath = projectPath(org, project, "traces/compare");
  const rawEnvironment = formData.get("environment");
  const environment = rawEnvironment === "" ? "" : typeof rawEnvironment === "string" ? resolveEnvironment(rawEnvironment) : undefined;
  const environmentParams: Record<string, string> = {};
  if (environment !== undefined) environmentParams.environment = environment;

  let errorMsg: string | null = null;
  try {
    if (!leftTraceId || !rightTraceId) throw new Error("Both traces are required");
    await compareTraces({ left_trace_id: leftTraceId, right_trace_id: rightTraceId });
  } catch (error) {
    errorMsg = messageFromActionError(error, "Failed to compare traces");
  }
  if (errorMsg) {
    redirectWithMessage(sourcePath, { error: errorMsg, ...environmentParams });
  }
  redirectWithMessage(comparePath, { left: leftTraceId, right: rightTraceId, ...environmentParams });
}

export async function createExportAction(formData: FormData): Promise<void> {
  const org = String(formData.get("org") ?? "");
  const project = String(formData.get("project") ?? "");
  const projectId = String(formData.get("project_id") ?? "");
  const environment = String(formData.get("environment") ?? "");
  const status = String(formData.get("status") ?? "");
  const nameContains = String(formData.get("name_contains") ?? "");
  const knownExportIds = String(formData.get("known_export_ids") ?? "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
  const path = projectPath(org, project, "exports");
  const filters: Record<string, unknown> = {};
  if (environment) filters.environment = environment;
  if (status) filters.status = status;
  if (nameContains) filters.name_contains = nameContains;

  let result: { export_id: string } | null = null;
  let errorMsg: string | null = null;
  try {
    result = await createExport({
      project_id: projectId,
      format: "jsonl",
      filters,
    });
    revalidatePath(path);
  } catch (error) {
    errorMsg = messageFromActionError(error, "Failed to create export");
  }
  if (result) {
    const ids = [result.export_id, ...knownExportIds.filter((id) => id !== result.export_id)].slice(0, 20);
    redirectWithMessage(path, { created: "1", export_id: result.export_id, ids: ids.join(",") });
  } else {
    redirectWithMessage(path, { error: errorMsg ?? "Failed to create export" });
  }
}

export async function markNotificationsReadAction(formData: FormData): Promise<void> {
  const org = String(formData.get("org") ?? "");
  const project = String(formData.get("project") ?? "");
  const projectId = String(formData.get("project_id") ?? "");
  const currentPath = String(formData.get("current_path") ?? "") || `/o/${org}/p/${project}`;
  const ids = formData.getAll("ids").map(String).filter(Boolean);

  let errorMsg: string | null = null;
  try {
    await markNotificationsRead(projectId, ids);
    revalidatePath(currentPath);
  } catch (error) {
    errorMsg = messageFromActionError(error, "Failed to mark notifications read");
  }
  redirectWithMessage(currentPath, errorMsg ? { error: errorMsg } : { notifications_read: "1" });
}

export async function setEnvironmentAction(formData: FormData): Promise<void> {
  const org = String(formData.get("org") ?? "");
  const project = String(formData.get("project") ?? "");
  const environment = String(formData.get("environment") ?? "prod");
  const currentPath = String(formData.get("current_path") ?? "") || `/o/${org}/p/${project}`;
  const store = await cookies();
  if (environment === "all") {
    store.delete(ENV_COOKIE);
    revalidatePath(currentPath);
    redirect(currentPath);
  }
  store.set({
    name: ENV_COOKIE,
    value: environment,
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 60 * 60 * 24 * 180,
  });
  revalidatePath(currentPath);
  // Pages (overview, traces, exports) read `searchParams.environment`. Using
  // the same key here makes the topbar selector immediately filter the page
  // data on top of persisting the choice in the cookie for future visits.
  redirectWithMessage(currentPath, { environment });
}

export async function createProjectAction(formData: FormData): Promise<void> {
  const org = String(formData.get("org") ?? "");
  const project = String(formData.get("project") ?? "");
  const orgId = String(formData.get("organization_id") ?? "");
  const name = String(formData.get("name") ?? "").trim();
  const slug = String(formData.get("slug") ?? "").trim();
  const descriptionRaw = String(formData.get("description") ?? "");
  const description = descriptionRaw.trim() === "" ? null : descriptionRaw;
  const defaultEnvironment = String(formData.get("default_environment") ?? "prod") as "dev" | "staging" | "prod";
  const errorPath = org && project ? `/o/${org}/p/${project}/settings` : org ? `/o/${org}` : "/";

  if (!orgId || !name || !slug) {
    redirectWithMessage(errorPath, { error: "Informe organização, nome e slug do projeto." });
  }

  let created: Awaited<ReturnType<typeof createProject>> | null = null;
  let errorMsg: string | null = null;
  try {
    created = await createProject({
      organization_id: orgId,
      name,
      slug,
      description,
      default_environment: defaultEnvironment,
    });
    revalidatePath(`/o/${org}`);
  } catch (error) {
    errorMsg = messageFromActionError(error, "Failed to create project");
  }
  if (created && org) {
    redirectWithMessage(`/o/${org}/p/${created.slug}/settings`, { created: "1" });
  }
  redirectWithMessage(errorPath, { error: errorMsg ?? "Failed to create project" });
}

export async function patchProjectAction(formData: FormData): Promise<void> {
  const org = String(formData.get("org") ?? "");
  const project = String(formData.get("project") ?? "");
  const projectId = String(formData.get("project_id") ?? "");
  const name = String(formData.get("name") ?? "");
  const descriptionRaw = String(formData.get("description") ?? "");
  const description = descriptionRaw.trim() === "" ? null : descriptionRaw;
  const defaultEnvironment = String(formData.get("default_environment") ?? "") as "dev" | "staging" | "prod" | "";
  const path = projectPath(org, project, "settings");

  let errorMsg: string | null = null;
  try {
    await patchProject(projectId, {
      name: name || undefined,
      description: formData.has("description") ? description : undefined,
      default_environment: defaultEnvironment || undefined,
    });
    revalidatePath(path);
    revalidatePath(`/o/${org}/p/${project}`);
  } catch (error) {
    errorMsg = messageFromActionError(error, "Failed to update project");
  }
  redirectWithMessage(path, errorMsg ? { error: errorMsg } : { updated: "1" });
}


export async function saveQualityGateAction(formData: FormData): Promise<void> {
  const org = String(formData.get("org") ?? "");
  const project = String(formData.get("project") ?? "");
  const path = projectPath(org, project, "settings");
  const config = parseQualityGateForm(formData);
  if (!config) redirectWithMessage(path, { error: "Dados inválidos. Verifique os limites do Quality Gate." });
  let errorMsg: string | null = null;
  try {
    // Resolve authenticated URL context; never trust a submitted project ID.
    const resolved = await resolveProject(org, project);
    await putQualityGateConfig(resolved.project_id, config);
    revalidatePath(path);
    revalidatePath(`/o/${org}/p/${project}`);
  } catch (error) {
    errorMsg = messageFromActionError(error, "Não foi possível salvar o Quality Gate.");
  }
  redirectWithMessage(path, errorMsg ? { error: errorMsg } : { gate_saved: "1" });
}

export async function saveSamplingAction(formData: FormData): Promise<void> {
  const org = String(formData.get("org") ?? "");
  const project = String(formData.get("project") ?? "");
  const path = projectPath(org, project, "settings");
  const enabled = formData.get("enabled") === "on";
  const rawPercentage = String(formData.get("percentage") ?? "").trim();
  const percentage = Number(rawPercentage);
  const rubricId = String(formData.get("rubric_id") ?? "").trim();
  const rawVersion = String(formData.get("rubric_version") ?? "").trim();
  const rubricVersion = rawVersion ? Number(rawVersion) : null;
  if (!rawPercentage || !Number.isFinite(percentage) || percentage < 0 || percentage > 100
    || (rubricVersion !== null && (!Number.isInteger(rubricVersion) || rubricVersion < 1))
    || Boolean(rubricId) !== (rubricVersion !== null) || (enabled && !rubricId)) {
    redirectWithMessage(path, { error: "Confira percentual, rubrica e versão da avaliação automática." });
  }
  let errorMsg: string | null = null;
  try {
    const resolved = await resolveProject(org, project);
    await putSamplingConfig(resolved.project_id, {
      enabled, percentage, rubric_id: rubricId || null, rubric_version: rubricVersion,
    });
    revalidatePath(path);
  } catch (error) {
    errorMsg = messageFromActionError(error, "Não foi possível salvar a avaliação automática.");
  }
  redirectWithMessage(path, errorMsg ? { error: errorMsg } : { sampling_saved: "1" });
}

export async function retrySamplingAction(formData: FormData): Promise<void> {
  const org = String(formData.get("org") ?? "");
  const project = String(formData.get("project") ?? "");
  const path = projectPath(org, project, "settings");
  const traceId = String(formData.get("trace_id") ?? "").trim();
  if (!traceId || traceId.length > 64) redirectWithMessage(path, { error: "Trace inválido." });
  let errorMsg: string | null = null;
  try {
    const resolved = await resolveProject(org, project);
    await retrySamplingJob(resolved.project_id, traceId, formData.get("confirm_possible_charge") === "on");
    revalidatePath(path);
  } catch (error) {
    errorMsg = messageFromActionError(error, "Não foi possível solicitar outra tentativa.");
  }
  redirectWithMessage(path, errorMsg ? { error: errorMsg } : { sampling_retried: "1" });
}
