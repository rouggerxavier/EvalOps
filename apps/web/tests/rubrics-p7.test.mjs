import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const page = readFileSync(
  new URL("../app/o/[org]/p/[project]/rubrics/page.tsx", import.meta.url),
  "utf8",
);
const actions = readFileSync(new URL("../lib/actions.ts", import.meta.url), "utf8");
const api = readFileSync(new URL("../lib/api.ts", import.meta.url), "utf8");

test("rubrics: page wires real server actions and API calls", () => {
  assert.match(page, /createRubricAction/);
  assert.match(page, /createRubricVersionAction/);
  assert.match(page, /getRubrics\(resolved\.project_id\)/);
  assert.match(page, /getRubricVersions\(/);
});

test("rubrics: forms expose backend-required fields", () => {
  assert.match(page, /action=\{createRubricAction\}/);
  assert.match(page, /action=\{createRubricVersionAction\}/);
  assert.match(page, /<RubricYamlEditor/);
  assert.match(page, /name="rubric_id"/);
  assert.match(page, /name="project_id"/);
});

test("rubrics: selected rubric shows the report (totals, versions, trend, evaluators)", () => {
  assert.match(page, /getRubricReport\(resolved\.project_id, selected\.id, reportWindow, environment\)/);
  assert.match(page, /getActiveEnvironment\(qp\.environment\)/);
  assert.match(page, /\?\? "7d"/);
  assert.match(page, /report\.by_version\.map/);
  assert.match(page, /report\.by_evaluator\.map/);
  assert.match(page, /<AreaChart data=\{trendSeries\}/);
  assert.match(page, /Nenhuma avaliação neste período/);
  // Existing definition and version history stay.
  assert.match(page, /latestVersion\?\.yaml_source \?\? "Sem dados de YAML/);
  assert.match(page, /\[\.\.\.versions\]\.reverse\(\)\.map\(\(version\)/);
});

test("rubrics: unknown and errored runs are never shown as passed", () => {
  assert.match(page, /pctOrDash\(report\.totals\.pass_rate\)/);
  assert.match(page, /report\.totals\.unknown \+ report\.totals\.errors/);
  assert.doesNotMatch(page, /passed \+ (?:report\.totals\.)?unknown/);
});

test("rubrics: batch form posts the action with labelled fields", () => {
  assert.match(page, /action=\{triggerEvaluationBatchAction\}/);
  for (const name of ["rubric_version", "environment", "limit", "name_contains", "project_id", "rubric_id"]) {
    assert.match(page, new RegExp(`name="${name}"`));
  }
  assert.match(page, /max=\{500\}/);
  assert.match(page, /Versão da rubrica<\/span>/);
  assert.match(page, /Máximo de traces<\/span>/);
  assert.match(page, /qp\.batched/);
});

test("rubrics: batch action maps a down worker (503) to a clear message", () => {
  assert.match(actions, /export async function triggerEvaluationBatchAction/);
  assert.match(actions, /startsWith\("API 503"\)/);
  assert.match(actions, /worker não está rodando/);
  assert.match(api, /\/projects\/\$\{projectId\}\/evaluations\/batch/);
  assert.match(api, /\/projects\/\$\{projectId\}\/rubrics\/\$\{rubricId\}\/report/);
});

test("rubrics: no preview-bundle leakage", () => {
  assert.doesNotMatch(page, /evalops-preview/);
  assert.doesNotMatch(page, /window\.MODULES/);
  assert.doesNotMatch(page, /PreviewActionModal/);
});
