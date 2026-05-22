import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const page = readFileSync(
  new URL("../app/o/[org]/p/[project]/page.tsx", import.meta.url),
  "utf8",
);

test("overview: server contract preserved (overview + traces + attention + coverage + rubrics)", () => {
  assert.match(page, /getOverview\(projectId, environment, window_\)/);
  assert.match(page, /getAttention\(projectId\)/);
  assert.match(page, /getCoverage\(projectId, window_\)/);
  assert.match(page, /getRubrics\(projectId\)/);
  assert.match(page, /getTraces\(\{[^}]*projectId/);
  assert.match(page, /resolveProject\(org, project\)/);
  assert.match(page, /hasAuthToken\(\)/);
  assert.match(page, /<AuthRequiredPanel/);
});

test("overview: window selector + refresh + evaluation actions wired to real components", () => {
  assert.match(page, /WindowSelect/);
  assert.match(page, /EvaluateHeaderButton/);
  assert.match(page, /title="Atualizar overview"/);
});

test("overview: AttentionStrip rendered only when attention.count > 0", () => {
  assert.match(page, /attention\.count > 0/);
  assert.match(page, /<AttentionStrip/);
});

test("overview: real KPI fields read from the overview response", () => {
  assert.match(page, /kpis\.cost_usd/);
  assert.match(page, /kpis\.error_rate/);
  assert.match(page, /kpis\.latency_p95_ms/);
});

test("overview: env reads from active-env helper (cookie + query fallback)", () => {
  assert.match(page, /getActiveEnvironment\(qp\.environment\)/);
});

test("overview: no preview-bundle leakage or mock metrics", () => {
  assert.doesNotMatch(page, /evalops-preview/);
  assert.doesNotMatch(page, /window\.MODULES/);
  assert.doesNotMatch(page, /PreviewActionModal/);
  assert.doesNotMatch(page, /errors_7d/);
});
