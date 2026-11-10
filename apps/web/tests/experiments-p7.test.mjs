import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const page = readFileSync(
  new URL("../app/o/[org]/p/[project]/experiments/page.tsx", import.meta.url),
  "utf8",
);

test("experiments: page wires real server actions and API calls", () => {
  assert.match(page, /createExperimentAction/);
  assert.match(page, /runExperimentAction/);
  assert.match(page, /getExperiments\(resolved\.project_id\)/);
  assert.match(page, /getDatasets\(resolved\.project_id\)/);
  assert.match(page, /getRubrics\(resolved\.project_id\)/);
  assert.match(page, /getExperimentRun\(qp\.experiment_id, qp\.run_id\)/);
});

test("experiments: forms expose backend-required fields", () => {
  assert.match(page, /action=\{createExperimentAction\}/);
  assert.match(page, /action=\{runExperimentAction\}/);
  assert.match(page, /name="name"/);
  assert.match(page, /name="baseline_variant"/);
  assert.match(page, /name="dataset_id"/);
  assert.match(page, /name="rubric_id"/);
  assert.match(page, /name="variants_json"/);
  assert.match(page, /name="pass_criteria_json"/);
  assert.match(page, /name="experiment_id"/);
  assert.match(page, /name="project_id"/);
});

test("experiments: run result uses API variant data and marks unsupported p95", () => {
  assert.match(page, /Resultado mais recente/);
  assert.match(page, /run\.by_variant/);
  assert.match(page, /metrics\.avg_score/);
  assert.match(page, /Latência p95: Sem dados/);
  assert.match(page, /const runIsSynthetic = true/);
  assert.match(page, /Resultado legado sintético/);
  assert.match(page, /avaliação por modelo ainda pode consumir orçamento/);
  assert.match(page, /criteria_failures/);
});

test("experiments: no preview-bundle leakage", () => {
  assert.doesNotMatch(page, /evalops-preview/);
  assert.doesNotMatch(page, /window\.MODULES/);
  assert.doesNotMatch(page, /PreviewActionModal/);
});

test("experiments: run history lists runs per experiment and reuses RunResultCard", () => {
  const api = readFileSync(new URL("../lib/api.ts", import.meta.url), "utf8");
  assert.match(api, /export async function getExperimentRuns\(experimentId: string, limit = 20\)/);
  assert.match(api, /\/experiments\/\$\{experimentId\}\/runs\?limit=\$\{limit\}/);
  assert.match(page, /getExperimentRuns\(qp\.experiment_id\)/);
  assert.match(page, /Histórico/);
  assert.match(page, /Nenhuma run ainda/);
  assert.match(page, /href=\{`\?experiment_id=\$\{run\.experiment_id\}&run_id=\$\{run\.id\}`\}/);
  assert.match(page, /href=\{`\?experiment_id=\$\{experiment\.id\}`\}/);
  assert.match(page, /<RunResultCard run=\{runDetail\.run\}/);
});
