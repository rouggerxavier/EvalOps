"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { isRedirectError } from "next/dist/client/components/redirect-error";

import {
  buildDatasetFromTraces,
  createApiKey,
  createDataset,
  createExport,
  createDatasetItems,
  createExperiment,
  createPrompt,
  createPromptVersion,
  createTraceFeedback,
  createRubric,
  createRubricVersion,
  revokeApiKey,
  runExperiment,
  triggerEvaluation,
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
  return error instanceof Error ? error.message : fallback;
}

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
    redirectWithMessage(path, { created: "1", key: result.key, prefix: result.prefix });
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

export async function createRubricAction(formData: FormData): Promise<void> {
  const org = String(formData.get("org") ?? "");
  const project = String(formData.get("project") ?? "");
  const projectId = String(formData.get("project_id") ?? "");
  const yamlSource = String(formData.get("yaml_source") ?? "");
  const path = projectPath(org, project, "rubrics");

  let errorMsg: string | null = null;
  try {
    await createRubric(projectId, yamlSource);
    revalidatePath(path);
  } catch (error) {
    errorMsg = messageFromActionError(error, "Failed to create rubric");
  }
  redirectWithMessage(path, errorMsg ? { error: errorMsg } : { created: "1" });
}

export async function createRubricVersionAction(formData: FormData): Promise<void> {
  const org = String(formData.get("org") ?? "");
  const project = String(formData.get("project") ?? "");
  const rubricId = String(formData.get("rubric_id") ?? "");
  const yamlSource = String(formData.get("yaml_source") ?? "");
  const path = projectPath(org, project, "rubrics");

  let errorMsg: string | null = null;
  try {
    await createRubricVersion(rubricId, yamlSource);
    revalidatePath(path);
  } catch (error) {
    errorMsg = messageFromActionError(error, "Failed to create rubric version");
  }
  redirectWithMessage(path, errorMsg ? { error: errorMsg } : { versioned: "1" });
}

export async function triggerEvaluationAction(formData: FormData): Promise<void> {
  const org = String(formData.get("org") ?? "");
  const project = String(formData.get("project") ?? "");
  const traceId = String(formData.get("trace_id") ?? "");
  const rubricId = String(formData.get("rubric_id") ?? "");
  const rubricVersionRaw = String(formData.get("rubric_version") ?? "").trim();
  const path = projectPath(org, project, "evaluations");

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
  redirectWithMessage(path, errorMsg ? { error: errorMsg } : { created: "1" });
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


