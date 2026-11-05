import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const page = readFileSync(
  new URL("../app/o/[org]/p/[project]/evaluations/page.tsx", import.meta.url),
  "utf8",
);
const distBars = readFileSync(
  new URL("../components/ui/DistBars.tsx", import.meta.url),
  "utf8",
);

function escaped(token) {
  return new RegExp(token.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
}

test("evaluations premium: keeps real endpoints and server actions", () => {
  for (const token of [
    "getProjectEvaluations(resolved.project_id, EVALUATION_RUNS_LIMIT, environment)",
    "getRubrics(resolved.project_id)",
    "resolveProject(org, project)",
  ]) {
    assert.match(page, escaped(token));
  }
});

test("evaluations premium: aggregates real run/rubric data, no mocks", () => {
  for (const token of [
    "aggregate_score",
    "cost_usd",
    "created_at",
    "passed",
    "EVALUATION_RUNS_LIMIT",
  ]) {
    assert.match(page, escaped(token));
  }
  assert.doesNotMatch(page, /Math\.random/);
  assert.doesNotMatch(page, /mock/i);
});

test("evaluations premium: DistBars is the shared component", () => {
  assert.match(page, /import \{ DistBars \}/);
  assert.match(distBars, /export function DistBars/);
});

test("evaluations premium: empty states stay honest", () => {
  assert.match(page, /Nenhuma rubrica cadastrada/);
  assert.doesNotMatch(page, /EndpointSnippet/);
  assert.doesNotMatch(page, /evalops-preview/);
});
