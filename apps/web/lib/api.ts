import type {
  AttentionResponse,
  ApiKey,
  ApiKeyCreateResponse,
  BulkTraceFlagResponse,
  CoverageResponse,
  Dataset,
  DatasetItem,
  Experiment,
  ExperimentRun,
  EvaluationSummary,
  EvaluationRun,
  ExportListResponse,
  ExportJob,
  HumanFeedback,
  Member,
  NotificationListResponse,
  OrgSubscription,
  OrgUsage,
  OverviewResponse,
  Project,
  Prompt,
  PromptUsage,
  PromptVersion,
  RagConsolidated,
  ResolvedProject,
  Rubric,
  RubricVersion,
  SdkStatus,
  TraceCompareResponse,
  TraceDetailResponse,
  TraceFlag,
  TraceListResponse,
  TraceRerunResponse,
} from "./types";
import { getAuthToken, getSession, hasFallbackToken } from "./auth";
import { getApiBaseUrl } from "./config";

async function authHeaders(): Promise<HeadersInit> {
  const token = await getAuthToken();
  if (!token) return {};
  return { Authorization: `Bearer ${token}` };
}

async function fetchJson<T>(path: string): Promise<T> {
  return requestJson<T>(path);
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const auth = await authHeaders();
  const res = await fetch(`${getApiBaseUrl()}${path}`, {
    method: init?.method ?? "GET",
    headers: {
      "Content-Type": "application/json",
      ...auth,
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
    body: init?.body,
  });
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${await res.text()}`);
  }
  return (await res.json()) as T;
}

export async function resolveProject(orgSlug: string, projectSlug: string): Promise<ResolvedProject> {
  const params = new URLSearchParams({ org_slug: orgSlug, project_slug: projectSlug });
  return fetchJson<ResolvedProject>(`/resolve?${params.toString()}`);
}

export function hasDashboardToken(): boolean {
  return hasFallbackToken();
}

export async function hasAuthToken(): Promise<boolean> {
  if (hasFallbackToken()) return true;
  return (await getSession()) !== null;
}

export async function getOverview(
  projectId: string,
  environment?: string,
  window?: "24h" | "7d" | "30d",
): Promise<OverviewResponse> {
  const params = new URLSearchParams({ project_id: projectId });
  if (environment) params.set("environment", environment);
  if (window) params.set("window", window);
  return fetchJson<OverviewResponse>(`/analytics/overview?${params.toString()}`);
}

export async function getAttention(projectId: string): Promise<AttentionResponse> {
  return fetchJson<AttentionResponse>(`/projects/${projectId}/attention`);
}

export async function getCoverage(
  projectId: string,
  window?: "24h" | "7d" | "30d",
): Promise<CoverageResponse> {
  const params = new URLSearchParams();
  if (window) params.set("window", window);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return fetchJson<CoverageResponse>(`/projects/${projectId}/coverage${suffix}`);
}

export async function getSdkStatus(projectId: string): Promise<SdkStatus> {
  return fetchJson<SdkStatus>(`/projects/${projectId}/sdk-status`);
}

export async function getNotifications(projectId: string, limit = 20): Promise<NotificationListResponse> {
  const params = new URLSearchParams({ limit: String(limit) });
  return fetchJson<NotificationListResponse>(`/projects/${projectId}/notifications?${params.toString()}`);
}

export async function markNotificationsRead(projectId: string, ids: string[]): Promise<{ updated: number }> {
  return requestJson<{ updated: number }>(`/projects/${projectId}/notifications/mark-read`, {
    method: "POST",
    body: JSON.stringify({ ids }),
  });
}

export async function getTraces(opts: {
  projectId: string;
  limit?: number;
  status?: string;
  environment?: string;
  name?: string;
  cursor?: string;
  duration_gt?: number;
  rag?: boolean;
}): Promise<TraceListResponse> {
  const params = new URLSearchParams({
    project_id: opts.projectId,
    limit: String(opts.limit ?? 50),
  });
  if (opts.status) params.set("status", opts.status);
  if (opts.environment) params.set("environment", opts.environment);
  if (opts.name) params.set("name", opts.name);
  if (opts.cursor) params.set("cursor", opts.cursor);
  if (opts.duration_gt !== undefined) params.set("duration_gt", String(opts.duration_gt));
  if (opts.rag !== undefined) params.set("rag", String(opts.rag));
  return fetchJson<TraceListResponse>(`/traces?${params.toString()}`);
}

export async function getTrace(traceId: string): Promise<TraceDetailResponse> {
  return fetchJson<TraceDetailResponse>(`/traces/${traceId}`);
}

export async function flagTrace(traceId: string, payload: {
  reason: string;
  note?: string;
}): Promise<TraceFlag> {
  return requestJson<TraceFlag>(`/traces/${traceId}/flags`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function bulkFlagTraces(payload: {
  trace_ids: string[];
  reason: string;
  note?: string;
}): Promise<BulkTraceFlagResponse> {
  return requestJson<BulkTraceFlagResponse>(`/traces/bulk-flag`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function rerunTrace(traceId: string, payload?: {
  model?: string;
  variables?: Record<string, unknown>;
}): Promise<TraceRerunResponse> {
  return requestJson<TraceRerunResponse>(`/traces/${traceId}/rerun`, {
    method: "POST",
    body: JSON.stringify(payload ?? {}),
  });
}

export async function compareTraces(payload: {
  left_trace_id: string;
  right_trace_id: string;
}): Promise<TraceCompareResponse> {
  return requestJson<TraceCompareResponse>(`/traces/compare`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getTraceRag(traceId: string): Promise<RagConsolidated> {
  return fetchJson<RagConsolidated>(`/traces/${traceId}/rag`);
}

export async function createTraceFeedback(traceId: string, payload: {
  source?: string;
  thumbs?: "up" | "down";
  rating?: number;
  comment?: string;
  tags?: string[];
  user_ref?: string;
  correction?: Record<string, unknown>;
}): Promise<{ feedback: HumanFeedback }> {
  return requestJson<{ feedback: HumanFeedback }>(`/traces/${traceId}/feedback`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getTraceFeedback(traceId: string): Promise<{ data: HumanFeedback[] }> {
  return fetchJson<{ data: HumanFeedback[] }>(`/traces/${traceId}/feedback`);
}

export async function getApiKeys(projectId: string): Promise<{ data: ApiKey[] }> {
  return fetchJson<{ data: ApiKey[] }>(`/projects/${projectId}/api-keys`);
}

export async function createApiKey(projectId: string, payload: {
  name: string;
  environment: "dev" | "staging" | "prod";
  scopes: string[];
}): Promise<ApiKeyCreateResponse> {
  return requestJson<ApiKeyCreateResponse>(`/projects/${projectId}/api-keys`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function revokeApiKey(projectId: string, keyId: string): Promise<void> {
  const res = await fetch(`${getApiBaseUrl()}/projects/${projectId}/api-keys/${keyId}/revoke`, {
    method: "POST",
    headers: await authHeaders(),
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${await res.text()}`);
  }
}

export async function getRubrics(projectId: string): Promise<{ data: Rubric[] }> {
  return fetchJson<{ data: Rubric[] }>(`/projects/${projectId}/rubrics`);
}

export async function createRubric(projectId: string, yamlSource: string): Promise<{
  rubric: Rubric;
  version: RubricVersion;
}> {
  return requestJson<{ rubric: Rubric; version: RubricVersion }>(`/projects/${projectId}/rubrics`, {
    method: "POST",
    body: JSON.stringify({ yaml_source: yamlSource }),
  });
}

export async function getRubricVersions(rubricId: string): Promise<{ data: RubricVersion[] }> {
  return fetchJson<{ data: RubricVersion[] }>(`/rubrics/${rubricId}/versions`);
}

export async function createRubricVersion(rubricId: string, yamlSource: string): Promise<{
  version: RubricVersion;
  rubric_version: number;
}> {
  return requestJson<{ version: RubricVersion; rubric_version: number }>(`/rubrics/${rubricId}/versions`, {
    method: "POST",
    body: JSON.stringify({ yaml_source: yamlSource }),
  });
}

export async function getProjectEvaluations(projectId: string, limit = 100): Promise<{ data: EvaluationRun[] }> {
  const params = new URLSearchParams({ limit: String(limit) });
  return fetchJson<{ data: EvaluationRun[] }>(`/projects/${projectId}/evaluations?${params.toString()}`);
}

export async function getEvaluationSummary(projectId: string): Promise<EvaluationSummary> {
  return fetchJson<EvaluationSummary>(`/projects/${projectId}/evaluations/summary`);
}

export async function getTraceEvaluations(traceId: string): Promise<{ data: EvaluationRun[] }> {
  return fetchJson<{ data: EvaluationRun[] }>(`/traces/${traceId}/evaluations`);
}

export async function triggerEvaluation(payload: {
  trace_id: string;
  rubric_id: string;
  rubric_version?: number;
  triggered_by?: string;
}): Promise<{ run: EvaluationRun }> {
  return requestJson<{ run: EvaluationRun }>(`/evaluations/run`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getPrompts(projectId: string): Promise<{ data: Prompt[] }> {
  return fetchJson<{ data: Prompt[] }>(`/projects/${projectId}/prompts`);
}

export async function createPrompt(projectId: string, payload: {
  slug: string;
  description?: string;
  template: string;
  variables?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  changelog?: string;
}): Promise<{ prompt: Prompt; version: PromptVersion }> {
  return requestJson<{ prompt: Prompt; version: PromptVersion }>(`/projects/${projectId}/prompts`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getPromptVersions(promptId: string): Promise<{ data: PromptVersion[] }> {
  return fetchJson<{ data: PromptVersion[] }>(`/prompts/${promptId}/versions`);
}

export async function getPromptUsage(promptId: string, limit = 50): Promise<PromptUsage> {
  const params = new URLSearchParams({ limit: String(limit) });
  return fetchJson<PromptUsage>(`/prompts/${promptId}/usage?${params.toString()}`);
}

export async function createPromptVersion(promptId: string, payload: {
  template: string;
  variables?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  changelog?: string;
}): Promise<{ version: PromptVersion; prompt_version: number }> {
  return requestJson<{ version: PromptVersion; prompt_version: number }>(`/prompts/${promptId}/versions`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getDatasets(projectId: string): Promise<{ data: Dataset[] }> {
  return fetchJson<{ data: Dataset[] }>(`/projects/${projectId}/datasets`);
}

export async function createDataset(projectId: string, payload: {
  slug: string;
  description?: string;
  source: string;
}): Promise<Dataset> {
  return requestJson<Dataset>(`/projects/${projectId}/datasets`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getDatasetItems(datasetId: string): Promise<{ data: DatasetItem[] }> {
  return fetchJson<{ data: DatasetItem[] }>(`/datasets/${datasetId}/items`);
}

export async function createDatasetItems(datasetId: string, payload: {
  items: Array<{
    input: Record<string, unknown>;
    expected_output?: Record<string, unknown> | null;
    metadata?: Record<string, unknown>;
  }>;
}): Promise<{ created: number }> {
  return requestJson<{ created: number }>(`/datasets/${datasetId}/items`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function buildDatasetFromTraces(datasetId: string, payload: {
  environment?: string;
  status?: string;
  limit?: number;
  name_contains?: string;
}): Promise<{ created: number; dataset_id: string }> {
  return requestJson<{ created: number; dataset_id: string }>(`/datasets/${datasetId}/build-from-traces`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getExperiments(projectId: string): Promise<{ data: Experiment[] }> {
  return fetchJson<{ data: Experiment[] }>(`/projects/${projectId}/experiments`);
}

export async function createExperiment(projectId: string, payload: {
  name: string;
  dataset_id: string;
  rubric_id: string;
  variants: Array<{
    name: string;
    prompt_version_ref?: string;
    model?: string;
    params?: Record<string, unknown>;
  }>;
  baseline_variant?: string;
  pass_criteria?: Record<string, unknown>;
}): Promise<Experiment> {
  return requestJson<Experiment>(`/projects/${projectId}/experiments`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function runExperiment(experimentId: string, payload?: {
  triggered_by?: string;
}): Promise<{ run_id: string; status: string; passed: boolean | null }> {
  return requestJson<{ run_id: string; status: string; passed: boolean | null }>(`/experiments/${experimentId}/run`, {
    method: "POST",
    body: JSON.stringify(payload ?? { triggered_by: "dashboard" }),
  });
}

export async function getExperimentRun(experimentId: string, runId: string): Promise<{ run: ExperimentRun }> {
  return fetchJson<{ run: ExperimentRun }>(`/experiments/${experimentId}/runs/${runId}`);
}

export async function createExport(payload: {
  project_id: string;
  format: "jsonl";
  filters?: Record<string, unknown>;
}): Promise<{ export_id: string; status: string }> {
  return requestJson<{ export_id: string; status: string }>(`/exports`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getExport(exportId: string): Promise<ExportJob> {
  return fetchJson<ExportJob>(`/exports/${exportId}`);
}

export async function listExports(projectId: string, limit = 50): Promise<ExportListResponse> {
  const params = new URLSearchParams({ limit: String(limit) });
  return fetchJson<ExportListResponse>(`/projects/${projectId}/exports?${params.toString()}`);
}

export function getExportDownloadPath(exportId: string, redirectPath: string): string {
  const params = new URLSearchParams({ redirect: redirectPath });
  return `/api/exports/${encodeURIComponent(exportId)}/download?${params.toString()}`;
}

export async function getOrganizationSubscription(orgId: string): Promise<OrgSubscription> {
  return fetchJson<OrgSubscription>(`/organizations/${orgId}/subscription`);
}

export async function getOrganizationUsage(orgId: string, period?: string): Promise<OrgUsage> {
  const params = new URLSearchParams();
  if (period) params.set("period", period);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return fetchJson<OrgUsage>(`/organizations/${orgId}/usage${suffix}`);
}

export async function getMembers(orgId: string): Promise<{ data: Member[] }> {
  return fetchJson<{ data: Member[] }>(`/organizations/${orgId}/members`);
}

export async function getProjects(orgId: string): Promise<{ data: Project[] }> {
  const params = new URLSearchParams({ organization_id: orgId });
  return fetchJson<{ data: Project[] }>(`/projects?${params.toString()}`);
}

export async function patchProject(projectId: string, payload: {
  name?: string;
  description?: string | null;
  default_environment?: "dev" | "staging" | "prod";
}): Promise<Project> {
  return requestJson<Project>(`/projects/${projectId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}
