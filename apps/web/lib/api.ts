import type { OverviewResponse, TraceDetailResponse, TraceListResponse } from "./types";

const API_BASE_URL = process.env.EVALOPS_API_BASE_URL ?? "http://localhost:8000/v1";
const DASH_TOKEN = process.env.EVALOPS_DASHBOARD_BEARER_TOKEN;

function authHeaders(): HeadersInit {
  if (!DASH_TOKEN) {
    return {};
  }
  return { Authorization: `Bearer ${DASH_TOKEN}` };
}

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${await res.text()}`);
  }
  return (await res.json()) as T;
}

export function hasDashboardToken(): boolean {
  return Boolean(DASH_TOKEN);
}

export async function getOverview(projectId: string, environment?: string): Promise<OverviewResponse> {
  const params = new URLSearchParams({ project_id: projectId });
  if (environment) params.set("environment", environment);
  return fetchJson<OverviewResponse>(`/analytics/overview?${params.toString()}`);
}

export async function getTraces(opts: {
  projectId: string;
  limit?: number;
  status?: string;
  environment?: string;
  name?: string;
}): Promise<TraceListResponse> {
  const params = new URLSearchParams({
    project_id: opts.projectId,
    limit: String(opts.limit ?? 50),
  });
  if (opts.status) params.set("status", opts.status);
  if (opts.environment) params.set("environment", opts.environment);
  if (opts.name) params.set("name", opts.name);
  return fetchJson<TraceListResponse>(`/traces?${params.toString()}`);
}

export async function getTrace(traceId: string): Promise<TraceDetailResponse> {
  return fetchJson<TraceDetailResponse>(`/traces/${traceId}`);
}
