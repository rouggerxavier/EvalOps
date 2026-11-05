import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const page = readFileSync(
  new URL("../app/o/[org]/p/[project]/rubrics/page.tsx", import.meta.url),
  "utf8",
);

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

test("rubrics: no preview-bundle leakage", () => {
  assert.doesNotMatch(page, /evalops-preview/);
  assert.doesNotMatch(page, /window\.MODULES/);
  assert.doesNotMatch(page, /PreviewActionModal/);
});
