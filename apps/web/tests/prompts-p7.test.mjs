import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const page = readFileSync(
  new URL("../app/o/[org]/p/[project]/prompts/page.tsx", import.meta.url),
  "utf8",
);

test("prompts: page wires real server actions and API calls", () => {
  assert.match(page, /createPromptAction/);
  assert.match(page, /createPromptVersionAction/);
  assert.match(page, /getPrompts\(resolved\.project_id\)/);
  assert.match(page, /getPromptVersions\(/);
});

test("prompts: forms expose backend-required fields", () => {
  assert.match(page, /action=\{createPromptAction\}/);
  assert.match(page, /action=\{createPromptVersionAction\}/);
  assert.match(page, /name="slug"/);
  assert.match(page, /name="template"/);
  assert.match(page, /name="variables_json"/);
  assert.match(page, /name="metadata_json"/);
  assert.match(page, /name="prompt_id"/);
});

test("prompts: DiffView keeps first-version + diff branches", () => {
  assert.match(page, /function DiffView/);
});

test("prompts: no preview-bundle leakage", () => {
  assert.doesNotMatch(page, /evalops-preview/);
  assert.doesNotMatch(page, /window\.MODULES/);
  assert.doesNotMatch(page, /PreviewActionModal/);
});
