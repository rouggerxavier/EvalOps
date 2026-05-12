"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

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

export async function createApiKeyAction(formData: FormData): Promise<void> {
  const org = String(formData.get("org") ?? "");
  const project = String(formData.get("project") ?? "");
  const projectId = String(formData.get("project_id") ?? "");
  const name = String(formData.get("name") ?? "");
  const environment = String(formData.get("environment") ?? "prod") as "dev" | "staging" | "prod";
  const scopes = formData.getAll("scopes").map(String);
  const path = projectPath(org, project, "keys");

  try {
    const created = await createApiKey(projectId, {
      name,
      environment,
      scopes: scopes.length > 0 ? scopes : ["ingest", "read"],
    });
    revalidatePath(path);
    redirectWithMessage(path, {
      created: "1",
      key: created.key,
      prefix: created.prefix,
    });
  } catch (error) {
    redirectWithMessage(path, { error: error instanceof Error ? error.message : "Failed to create API key" });
  }
}

export async function revokeApiKeyAction(formData: FormData): Promise<void> {
  const org = String(formData.get("org") ?? "");
  const project = String(formData.get("project") ?? "");
  const projectId = String(formData.get("project_id") ?? "");
  const keyId = String(formData.get("key_id") ?? "");
  const path = projectPath(org, project, "keys");

  try {
    await revokeApiKey(projectId, keyId);
    revalidatePath(path);
    redirectWithMessage(path, { revoked: "1" });
  } catch (error) {
    redirectWithMessage(path, { error: error instanceof Error ? error.message : "Failed to revoke API key" });
  }
}

export async function createRubricAction(formData: FormData): Promise<void> {
  const org = String(formData.get("org") ?? "");
  const project = String(formData.get("project") ?? "");
  const projectId = String(formData.get("project_id") ?? "");
  const yamlSource = String(formData.get("yaml_source") ?? "");
  const path = projectPath(org, project, "rubrics");

  try {
    await createRubric(projectId, yamlSource);
    revalidatePath(path);
    redirectWithMessage(path, { created: "1" });
  } catch (error) {
    redirectWithMessage(path, { error: error instanceof Error ? error.message : "Failed to create rubric" });
  }
}

export async function createRubricVersionAction(formData: FormData): Promise<void> {
  const org = String(formData.get("org") ?? "");
  const project = String(formData.get("project") ?? "");
  const rubricId = String(formData.get("rubric_id") ?? "");
  const yamlSource = String(formData.get("yaml_source") ?? "");
  const path = projectPath(org, project, "rubrics");

  try {
    await createRubricVersion(rubricId, yamlSource);
    revalidatePath(path);
    redirectWithMessage(path, { versioned: "1" });
  } catch (error) {
    redirectWithMessage(path, { error: error instanceof Error ? error.message : "Failed to create rubric version" });
  }
}

export async function triggerEvaluationAction(formData: FormData): Promise<void> {
  const org = String(formData.get("org") ?? "");
  const project = String(formData.get("project") ?? "");
  const traceId = String(formData.get("trace_id") ?? "");
  const rubricId = String(formData.get("rubric_id") ?? "");
  const rubricVersionRaw = String(formData.get("rubric_version") ?? "").trim();
  const path = projectPath(org, project, "evaluations");

  try {
    await triggerEvaluation({
      trace_id: traceId,
      rubric_id: rubricId,
      rubric_version: rubricVersionRaw ? Number(rubricVersionRaw) : undefined,
      triggered_by: "dashboard",
    });
    revalidatePath(path);
    redirectWithMessage(path, { created: "1" });
  } catch (error) {
    redirectWithMessage(path, { error: error instanceof Error ? error.message : "Failed to run evaluation" });
  }
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
    redirectWithMessage(path, { created: "1" });
  } catch (error) {
    redirectWithMessage(path, { error: error instanceof Error ? error.message : "Failed to create prompt" });
  }
}

export async function createPromptVersionAction(formData: FormData): Promise<void> {
  const org = String(formData.get("org") ?? "");
  const project = String(formData.get("project") ?? "");
  const promptId = String(formData.get("prompt_id") ?? "");
  const template = String(formData.get("template") ?? "");
  const variablesRaw = String(formData.get("variables_json") ?? "{}");
  const metadataRaw = String(formData.get("metadata_json") ?? "{}");
  const path = projectPath(org, project, "prompts");

  try {
    await createPromptVersion(promptId, {
      template,
      variables: JSON.parse(variablesRaw),
      metadata: JSON.parse(metadataRaw),
      changelog: "Updated from dashboard",
    });
    revalidatePath(path);
    redirectWithMessage(path, { versioned: "1" });
  } catch (error) {
    redirectWithMessage(path, { error: error instanceof Error ? error.message : "Failed to create prompt version" });
  }
}

export async function createDatasetAction(formData: FormData): Promise<void> {
  const org = String(formData.get("org") ?? "");
  const project = String(formData.get("project") ?? "");
  const projectId = String(formData.get("project_id") ?? "");
  const slug = String(formData.get("slug") ?? "");
  const description = String(formData.get("description") ?? "");
  const source = String(formData.get("source") ?? "manual");
  const path = projectPath(org, project, "datasets");

  try {
    await createDataset(projectId, {
      slug,
      description: description || undefined,
      source,
    });
    revalidatePath(path);
    redirectWithMessage(path, { created: "1" });
  } catch (error) {
    redirectWithMessage(path, { error: error instanceof Error ? error.message : "Failed to create dataset" });
  }
}

export async function addDatasetItemAction(formData: FormData): Promise<void> {
  const org = String(formData.get("org") ?? "");
  const project = String(formData.get("project") ?? "");
  const datasetId = String(formData.get("dataset_id") ?? "");
  const inputRaw = String(formData.get("input_json") ?? "{}");
  const expectedRaw = String(formData.get("expected_output_json") ?? "{}");
  const metadataRaw = String(formData.get("metadata_json") ?? "{}");
  const path = projectPath(org, project, "datasets");

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
    redirectWithMessage(path, { items_added: "1" });
  } catch (error) {
    redirectWithMessage(path, { error: error instanceof Error ? error.message : "Failed to add dataset item" });
  }
}

export async function buildDatasetFromTracesAction(formData: FormData): Promise<void> {
  const org = String(formData.get("org") ?? "");
  const project = String(formData.get("project") ?? "");
  const datasetId = String(formData.get("dataset_id") ?? "");
  const environment = String(formData.get("environment") ?? "");
  const status = String(formData.get("status") ?? "");
  const limitRaw = String(formData.get("limit") ?? "50");
  const path = projectPath(org, project, "datasets");

  try {
    await buildDatasetFromTraces(datasetId, {
      environment: environment || undefined,
      status: status || undefined,
      limit: Number(limitRaw) || 50,
    });
    revalidatePath(path);
    redirectWithMessage(path, { built: "1" });
  } catch (error) {
    redirectWithMessage(path, { error: error instanceof Error ? error.message : "Failed to build dataset from traces" });
  }
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
    redirectWithMessage(path, { created: "1" });
  } catch (error) {
    redirectWithMessage(path, { error: error instanceof Error ? error.message : "Failed to create experiment" });
  }
}

export async function runExperimentAction(formData: FormData): Promise<void> {
  const org = String(formData.get("org") ?? "");
  const project = String(formData.get("project") ?? "");
  const experimentId = String(formData.get("experiment_id") ?? "");
  const path = projectPath(org, project, "experiments");

  try {
    const res = await runExperiment(experimentId, { triggered_by: "dashboard" });
    revalidatePath(path);
    redirectWithMessage(path, { run: "1", run_id: res.run_id, experiment_id: experimentId });
  } catch (error) {
    redirectWithMessage(path, { error: error instanceof Error ? error.message : "Failed to run experiment" });
  }
}

export async function createTraceFeedbackAction(formData: FormData): Promise<void> {
  const org = String(formData.get("org") ?? "");
  const project = String(formData.get("project") ?? "");
  const traceId = String(formData.get("trace_id") ?? "");
  const thumbs = String(formData.get("thumbs") ?? "");
  const comment = String(formData.get("comment") ?? "");
  const path = projectPath(org, project, `traces/${traceId}`);

  try {
    await createTraceFeedback(traceId, {
      source: "dashboard",
      thumbs: thumbs === "up" || thumbs === "down" ? thumbs : undefined,
      comment: comment || undefined,
    });
    revalidatePath(path);
    redirectWithMessage(path, { feedback: "1" });
  } catch (error) {
    redirectWithMessage(path, { error: error instanceof Error ? error.message : "Failed to create feedback" });
  }
}

export async function createExportAction(formData: FormData): Promise<void> {
  const org = String(formData.get("org") ?? "");
  const project = String(formData.get("project") ?? "");
  const projectId = String(formData.get("project_id") ?? "");
  const environment = String(formData.get("environment") ?? "");
  const status = String(formData.get("status") ?? "");
  const path = projectPath(org, project, "exports");
  const filters: Record<string, unknown> = {};
  if (environment) filters.environment = environment;
  if (status) filters.status = status;

  try {
    const res = await createExport({
      project_id: projectId,
      format: "jsonl",
      filters,
    });
    revalidatePath(path);
    redirectWithMessage(path, { created: "1", export_id: res.export_id });
  } catch (error) {
    redirectWithMessage(path, { error: error instanceof Error ? error.message : "Failed to create export" });
  }
}
