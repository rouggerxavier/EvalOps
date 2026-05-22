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

test("experiments: run result block surfaces criteria + variant breakdown", () => {
  assert.match(page, /Resultado da run/);
  assert.match(page, /criteria_failures/);
  assert.match(page, /by_variant/);
});

test("experiments: no preview-bundle leakage", () => {
  assert.doesNotMatch(page, /evalops-preview/);
  assert.doesNotMatch(page, /window\.MODULES/);
  assert.doesNotMatch(page, /PreviewActionModal/);
});
