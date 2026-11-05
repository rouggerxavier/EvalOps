import { getAuthToken } from "@/lib/auth";
import { getApiBaseUrl } from "@/lib/config";

export type RubricReportTotals = {
  runs: number;
  passed: number;
  failed: number;
  unknown: number;
  errors: number;
  pass_rate: number | null;
  avg_score: number | null;
  score_stddev: number | null;
  cost_usd: number;
};

export type RubricReport = {
  rubric_id: string;
  window: string;
  environment: string | null;
  totals: RubricReportTotals;
  by_day: Array<RubricReportTotals & { day: string; rubric_version: number }>;
};

export async function getRubricReport(
  projectId: string,
  rubricId: string,
  window = "7d",
  environment?: string,
): Promise<RubricReport> {
  const params = new URLSearchParams({ window });
  if (environment) params.set("environment", environment);
  const token = await getAuthToken();
  const response = await fetch(
    `${getApiBaseUrl()}/projects/${projectId}/rubrics/${rubricId}/report?${params.toString()}`,
    {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      cache: "no-store",
    },
  );
  if (!response.ok) throw new Error(`API ${response.status}`);
  return (await response.json()) as RubricReport;
}
