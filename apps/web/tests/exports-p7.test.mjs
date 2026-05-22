import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const page = readFileSync(
  new URL("../app/o/[org]/p/[project]/exports/page.tsx", import.meta.url),
  "utf8",
);

test("exports: page wires real server actions and API calls", () => {
  assert.match(page, /createExportAction/);
  assert.match(page, /listExports\(resolvedProject\.project_id\)/);
  assert.match(page, /getOrganizationUsage\(resolvedProject\.org_id\)/);
  assert.match(page, /getOrganizationSubscription\(resolvedProject\.org_id\)/);
});

test("exports: create form preserves required hidden fields", () => {
  assert.match(page, /action=\{createExportAction\}/);
  assert.match(page, /name="environment"/);
  assert.match(page, /name="status"/);
  assert.match(page, /name="name_contains"/);
  assert.match(page, /name="project_id"/);
  assert.match(page, /name="known_export_ids"/);
});

test("exports: file size column reads from job.file_size_bytes via formatBytes", () => {
  assert.match(page, /formatBytes\(row\.job\.file_size_bytes\)/);
});

test("exports: download path + sanitised error path preserved", () => {
  assert.match(page, /getExportDownloadPath\(row\.job\.id, currentViewHref\)/);
  assert.match(page, /safeErrorMessage\(/);
});

test("exports: no preview-bundle leakage", () => {
  assert.doesNotMatch(page, /evalops-preview/);
  assert.doesNotMatch(page, /window\.MODULES/);
  assert.doesNotMatch(page, /PreviewActionModal/);
});
