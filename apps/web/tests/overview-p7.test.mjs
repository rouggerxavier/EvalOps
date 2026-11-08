import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const page = readFileSync(
  new URL("../app/o/[org]/p/[project]/page.tsx", import.meta.url),
  "utf8",
);

test("overview: server contract uses overview, attention, traces and rubric reports", () => {
  assert.match(page, /getOverview\(projectId, environment, window_\)/);
  assert.match(page, /getAttention\(projectId\)/);
  assert.match(page, /getRubrics\(projectId\)/);
  assert.match(page, /getRubricReport\(projectId, rubric\.id, window_, environment\)/);
  assert.match(page, /getTraces\(\{[^}]*projectId/);
  assert.match(page, /resolveProject\(org, project\)/);
  assert.match(page, /hasAuthToken\(\)/);
  assert.match(page, /<AuthRequiredPanel/);
});

test("overview: period, refresh, export and evaluation actions use real routes/components", () => {
  assert.match(page, /WindowSelect/);
  assert.match(page, /OverviewMobileFilters/);
  assert.match(page, /EvaluateHeaderButton/);
  assert.match(page, /exportHref = `\/o\/\$\{org\}\/p\/\$\{project\}\/exports`/);
  assert.match(page, /refreshHref = `\/o\/\$\{org\}\/p\/\$\{project\}\?window=/);
});

test("overview: API gaps remain visible and attention uses its capped endpoint data", () => {
  assert.match(page, /attention\.count >= 25/);
  assert.match(page, /A API lista no máximo 25 traces/);
  assert.match(page, /Sem dados de aprovação no período selecionado/);
  assert.match(page, /todos os ambientes/);
  assert.doesNotMatch(page, /severity|prior period|vs\./i);
});

test("overview: real KPI fields read from the overview response", () => {
  assert.match(page, /kpis\.cost_usd/);
  assert.match(page, /kpis\.error_rate/);
  assert.match(page, /kpis\.latency_p95_ms/);
});

test("overview: env reads from active-env helper and period defaults to 24 hours", () => {
  assert.match(page, /getActiveEnvironment\(query\.environment\)/);
  assert.match(page, /return "24h"/);
});

test("overview: no preview-bundle leakage or mock metrics", () => {
  assert.doesNotMatch(page, /evalops-preview/);
  assert.doesNotMatch(page, /window\.MODULES/);
  assert.doesNotMatch(page, /PreviewActionModal/);
  assert.doesNotMatch(page, /errors_7d/);
});
