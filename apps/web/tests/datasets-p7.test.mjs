import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const page = readFileSync(
  new URL("../app/o/[org]/p/[project]/datasets/page.tsx", import.meta.url),
  "utf8",
);
const itemForm = readFileSync(
  new URL("../app/o/[org]/p/[project]/datasets/DatasetItemForm.tsx", import.meta.url),
  "utf8",
);

test("datasets: page wires real server actions and API calls", () => {
  assert.match(page, /addDatasetItemAction/);
  assert.match(page, /buildDatasetFromTracesAction/);
  assert.match(page, /createDatasetAction/);
  assert.match(page, /getDatasets\(resolved\.project_id\)/);
});

test("datasets: forms expose required fields per backend contract", () => {
  assert.match(page, /action=\{createDatasetAction\}/);
  assert.match(page, /action=\{buildDatasetFromTracesAction\}/);
  assert.match(page, /name="slug"/);
  assert.match(page, /name="project_id"/);
  assert.match(page, /formData\.set\("input_json"/);
  assert.match(page, /formData\.set\("expected_output_json"/);
  assert.match(page, /formData\.set\("metadata_json"/);
  assert.match(page, /<DatasetItemForm/);
  assert.match(itemForm, /action=\{action\}/);
  assert.match(itemForm, /name="dataset_id"/);
  assert.match(itemForm, /name="question"/);
  assert.match(itemForm, /name="expected_answer"/);
});

test("datasets: planned 'Exportar dataset' placeholder removed (Fase 7)", () => {
  assert.doesNotMatch(page, /Acoes nao disponiveis no contrato atual/);
  assert.doesNotMatch(page, /Exportar dataset/);
});

test("datasets: no preview-bundle leakage", () => {
  assert.doesNotMatch(page, /evalops-preview/);
  assert.doesNotMatch(page, /window\.MODULES/);
  assert.doesNotMatch(page, /PreviewActionModal/);
});
