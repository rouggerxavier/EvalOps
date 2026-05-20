import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const evaluationsPage = readFileSync(new URL("../app/o/[org]/p/[project]/evaluations/page.tsx", import.meta.url), "utf8");
const distBars = readFileSync(new URL("../components/DistBars.tsx", import.meta.url), "utf8");
const rubricDrawer = readFileSync(new URL("../components/RubricDrawer.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");

function escaped(token) {
  return new RegExp(token.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
}

test("P4 Evaluations premium: keeps real endpoints and server actions", () => {
  for (const token of [
    "getProjectEvaluations(resolved.project_id, EVALUATION_RUNS_LIMIT)",
    "getRubrics(resolved.project_id)",
    "getTraces({ projectId: resolved.project_id, limit: 20 })",
    "getRubricVersions(selectedRubric.id)",
    "triggerEvaluationAction",
    "resolveProject(org, project)",
  ]) {
    assert.match(evaluationsPage, escaped(token));
  }
});

test("P4 Evaluations premium: summary KPIs come from loaded run and rubric data", () => {
  for (const token of [
    "runs7d",
    "overallPassRate",
    "costUsd",
    "cost_usd",
    "created_at",
    "passed",
    "EVALUATION_RUNS_LIMIT",
    "Fonte: getRubrics",
    "Fonte: runs carregadas",
    "Custo carregado",
  ]) {
    assert.match(evaluationsPage, escaped(token));
  }
  assert.doesNotMatch(evaluationsPage, /health score/i);
  assert.doesNotMatch(evaluationsPage, /mock/i);
});

test("P4 Evaluations premium: DistBars is extracted and reused", () => {
  assert.match(evaluationsPage, /import \{ DistBars \}/);
  assert.doesNotMatch(evaluationsPage, /function DistBars/);
  assert.match(distBars, /export function DistBars/);
  assert.match(distBars, /role="img"/);
  assert.match(css, /\.dist-bars/);
  assert.match(css, /\.dist-bar--high/);
});

test("P4 Evaluations premium: rubric drawer is read-only and bounded for large YAML", () => {
  assert.match(evaluationsPage, /import \{ RubricDrawer \}/);
  assert.match(evaluationsPage, /rubric=\{selectedRubric\}/);
  assert.match(rubricDrawer, /yaml_source/);
  assert.match(rubricDrawer, /data-mode="read-only"/);
  assert.match(rubricDrawer, /evo-rubric-drawer__code/);
  assert.match(css, /\.evo-rubric-drawer__yaml[\s\S]*max-height:\s*420px/);
  assert.match(css, /@media \(max-width: 760px\)[\s\S]*\.evo-rubric-drawer__yaml/);
});

test("P4 Evaluations premium: empty states and planned controls stay honest", () => {
  for (const token of [
    "Nenhuma rubrica cadastrada",
    "Criar rubrica",
    "Rodar agora",
    "traces.length === 0",
    "Ver traces",
    "data-status=\"planned\"",
    "disabled",
    "href=\"#run-evaluation\"",
  ]) {
    assert.match(evaluationsPage, escaped(token));
  }
  assert.doesNotMatch(evaluationsPage, /EndpointSnippet/);
  assert.doesNotMatch(evaluationsPage, /evalops-preview/);
  assert.doesNotMatch(`${evaluationsPage}\n${distBars}\n${rubricDrawer}`, /data\.jsx/);
});
