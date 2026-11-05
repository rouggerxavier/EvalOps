import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const page = readFileSync(
  new URL("../app/o/[org]/p/[project]/evaluations/page.tsx", import.meta.url),
  "utf8",
);
const modals = readFileSync(
  new URL("../app/o/[org]/p/[project]/evaluations/evaluations-modals.tsx", import.meta.url),
  "utf8",
);

test("evaluations: page wires real server data", () => {
  for (const token of [
    "getProjectEvaluations(resolved.project_id, EVALUATION_RUNS_LIMIT, environment)",
    "getRubrics(resolved.project_id)",
    "resolveProject(org, project)",
    "hasAuthToken()",
    "<AuthRequiredPanel",
  ]) {
    assert.ok(page.includes(token), `expected evaluations page to keep ${token}`);
  }
});

test("evaluations: trigger form lives in the modals client component", () => {
  assert.match(modals, /triggerEvaluationAction/);
  assert.match(modals, /action=\{triggerEvaluationAction\}/);
});

test("evaluations: DistBars shared component preserved", () => {
  assert.match(page, /import \{ DistBars \}/);
  assert.match(page, /<DistBars/);
});

test("evaluations: aggregates real evaluation scores (no random data)", () => {
  assert.doesNotMatch(page, /Math\.random/);
  assert.doesNotMatch(page, /PreviewActionModal/);
  assert.match(page, /aggregate_score/);
});

test("evaluations: empty states render honest copy", () => {
  assert.match(page, /Nenhuma rubrica cadastrada/);
});
