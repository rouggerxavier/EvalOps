import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const overviewPage = readFileSync(new URL("../app/o/[org]/p/[project]/page.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");

function escaped(token) {
  return new RegExp(token.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
}

test("P3 Overview premium: uses existing real frontend data sources", () => {
  for (const token of [
    "getOverview(projectId, environment)",
    "getTraces({ projectId, limit: 8, environment })",
    "getProjectEvaluations(projectId, 25)",
    "getRubrics(projectId)",
    "resolveProject(org, project)",
    "recent_flagged",
    "model_breakdown",
    "kpis.avg_score",
  ]) {
    assert.match(overviewPage, escaped(token));
  }
});

test("P3 Overview premium: keeps CTAs on real AppShell routes", () => {
  for (const route of [
    "/traces",
    "/evaluations",
    "/rubrics",
    "/datasets",
    "/prompts",
    "/keys",
    "/exports",
  ]) {
    assert.match(overviewPage, escaped(`/o/${"${org}"}/p/${"${project}"}${route}`));
  }
  assert.match(overviewPage, /data-status="planned"/);
  assert.match(overviewPage, /disabled/);
});

test("P3 Overview premium: empty states are honest when sources are empty", () => {
  for (const token of [
    "Nenhum trace recente",
    "Nenhuma run de avaliacao",
    "Nenhuma rubrica cadastrada",
    "Sem serie diaria",
    "Sem fonte de score no payload",
    "Sem traces neste ambiente",
  ]) {
    assert.match(overviewPage, escaped(token));
  }
  assert.doesNotMatch(overviewPage, /fallbackSeries/);
  assert.doesNotMatch(overviewPage, /asSpark/);
});

test("P3 Overview premium: avoids preview mocks and fake metric language", () => {
  assert.doesNotMatch(overviewPage, /data\.jsx/);
  assert.doesNotMatch(overviewPage, /EndpointSnippet/);
  assert.doesNotMatch(overviewPage, /evalops-preview/);
  assert.doesNotMatch(overviewPage, /DocOps/i);
  assert.doesNotMatch(overviewPage, /health score/i);
  assert.doesNotMatch(overviewPage, /coverage/i);
  assert.doesNotMatch(overviewPage, /Attention/);
  assert.doesNotMatch(overviewPage, /Zone\.Identifier/);
});

test("P3 Overview premium: CSS is scoped to evo overview classes and responsive", () => {
  for (const selector of [
    ".evo-overview-page",
    ".evo-overview-hero",
    ".evo-overview-metric-grid",
    ".evo-overview-actions",
    ".evo-overview-main-grid",
    ".evo-overview-shortcuts",
  ]) {
    assert.match(css, escaped(selector));
  }
  assert.match(css, /@media \(max-width: 1120px\)[\s\S]*\.evo-overview-hero/);
  assert.match(css, /@media \(max-width: 760px\)[\s\S]*\.evo-overview-metric-grid/);
  assert.doesNotMatch(css, /:root\s*\{\s*--evo-overview/);
});
