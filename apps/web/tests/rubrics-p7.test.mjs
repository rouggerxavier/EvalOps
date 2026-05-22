import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const page = readFileSync(
  new URL("../app/o/[org]/p/[project]/rubrics/page.tsx", import.meta.url),
  "utf8",
);
const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");

test("P7.2 rubrics: page preserves server contract and real APIs", () => {
  assert.match(page, /import \{ createRubricAction, createRubricVersionAction \}/);
  assert.match(page, /import \{ getRubrics, getRubricVersions, hasAuthToken, resolveProject \}/);
  assert.match(page, /await getRubrics\(resolved\.project_id\)/);
  assert.match(page, /await getRubricVersions\(selected\.id\)/);
});

test("P7.2 rubrics: header keeps eyebrow + subtitle from P5", () => {
  assert.match(page, /evo-page-header__eyebrow[^>]*>Operação · Rubrics/);
  assert.match(page, /evo-page-header__title/);
  assert.match(page, /evo-page-header__subtitle/);
});

test("P7.2 rubrics: summary row uses only real payload-derived values", () => {
  assert.match(page, /<section className="evo-summary-row"/);
  assert.match(page, /Rubricas<\/p>/);
  assert.match(page, /\{totalRubrics\.toLocaleString\("pt-BR"\)\}/);
  assert.match(page, /\{totalVersions\.toLocaleString\("pt-BR"\)\}/);
  assert.match(page, /latestActivity \? relTime\(latestActivity\) : "—"/);
  // No invented metrics
  assert.doesNotMatch(page, /avgScore/);
  assert.doesNotMatch(page, /errors_7d/);
  assert.doesNotMatch(page, /attentionDot/);
});

test("P7.2 rubrics: forms (create + new version) preserved", () => {
  assert.match(page, /action=\{createRubricAction\}/);
  assert.match(page, /action=\{createRubricVersionAction\}/);
  assert.match(page, /name="yaml_source"/);
  assert.match(page, /name="rubric_id"/);
  assert.match(page, /name="project_id"/);
});

test("P7.2 rubrics: YAML block + VersionsList preserved", () => {
  assert.match(page, /function YamlBlock\(\{ code \}/);
  assert.match(page, /function VersionsList\(\{ versions, currentVersion \}/);
  assert.match(page, /latestVersion\?\.yaml_source/);
});

test("P7.2 rubrics: internal endpoints card removed from UI", () => {
  assert.doesNotMatch(page, /Endpoints ativos/);
  assert.doesNotMatch(page, /endpoint-list/);
  assert.doesNotMatch(page, /endpoint-row/);
  assert.doesNotMatch(page, /Funcionalidade preservada/);
  assert.doesNotMatch(page, /módulo preservado/);
  assert.doesNotMatch(page, /PreviewActionModal/);
  assert.doesNotMatch(page, /PreviewPill/);
});

test("P7.2 rubrics: planned controls keep disabled data-status='planned'", () => {
  assert.match(page, /data-status="planned"/);
  assert.match(page, /disabled/);
});

test("P7.2 CSS: summary/endpoint primitives still scoped to .evo-shell", () => {
  assert.match(css, /\.evo-shell \.evo-summary-row \{/);
  assert.match(css, /\.evo-shell \.evo-summary-card \{/);
  assert.match(css, /\.evo-shell \.evo-endpoint-list \{/);
  assert.match(css, /\.evo-shell \.evo-endpoint-row \{/);
  assert.doesNotMatch(css, /^\.evo-summary-row \{/m);
  assert.doesNotMatch(css, /^\.evo-endpoint-row \{/m);
});

test("P7.2 rubrics: no preview bundle import or design ZIP mock leakage", () => {
  assert.doesNotMatch(page, /evalops-preview/);
  assert.doesNotMatch(page, /data\.jsx/);
  assert.doesNotMatch(page, /window\.MODULES/);
});
