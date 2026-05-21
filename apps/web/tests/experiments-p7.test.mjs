import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const page = readFileSync(
  new URL("../app/o/[org]/p/[project]/experiments/page.tsx", import.meta.url),
  "utf8",
);
const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");

test("P7.4 experiments: page preserves server contract and real APIs", () => {
  assert.match(
    page,
    /import \{ createExperimentAction, runExperimentAction \}/,
  );
  assert.match(
    page,
    /getDatasets,\s*getExperimentRun,\s*getExperiments,\s*getRubrics,\s*hasAuthToken,\s*resolveProject,/,
  );
  assert.match(page, /getExperiments\(resolved\.project_id\)/);
  assert.match(page, /getDatasets\(resolved\.project_id\)/);
  assert.match(page, /getRubrics\(resolved\.project_id\)/);
  assert.match(page, /getExperimentRun\(qp\.experiment_id, qp\.run_id\)/);
});

test("P7.4 experiments: header keeps eyebrow + subtitle from P5", () => {
  assert.match(page, /evo-page-header__eyebrow[^>]*>Operação · Experimentos/);
  assert.match(page, /evo-page-header__title/);
  assert.match(page, /evo-page-header__subtitle/);
});

test("P7.4 experiments: summary row uses only real payload-derived values", () => {
  assert.match(page, /<section className="evo-summary-row"/);
  assert.match(page, /Experimentos<\/p>/);
  assert.match(page, /\{experiments\.length\.toLocaleString\("pt-BR"\)\}/);
  assert.match(page, /\{totalVariants\.toLocaleString\("pt-BR"\)\}/);
  assert.match(page, /\{withBaseline\.toLocaleString\("pt-BR"\)\}/);
  assert.match(page, /latestActivity \? relTime\(latestActivity\) : "—"/);
  // No invented metrics
  assert.doesNotMatch(page, /avgScore[^_]/);
  assert.doesNotMatch(page, /errors_7d/);
  assert.doesNotMatch(page, /attentionDot/);
});

test("P7.4 experiments: forms (create, run) preserved with required fields", () => {
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

test("P7.4 experiments: run result card + variants table preserved", () => {
  assert.match(page, /function RunResultCard\(/);
  assert.match(page, /Resultado da run/);
  assert.match(page, /criteria_failures/);
  assert.match(page, /by_variant/);
});

test("P7.4 experiments: endpoints reference card is read-only (no modal preview)", () => {
  assert.match(page, /<h3 className="evo-card__title">Endpoints ativos<\/h3>/);
  assert.match(page, /aria-label="Endpoints do módulo Experiments"/);
  assert.match(page, /evo-endpoint-row__method--get/);
  assert.match(page, /evo-endpoint-row__method--post/);
  assert.match(page, /\/experiments\/\{"\{experiment_id\}"\}\/run/);
  assert.match(page, /\/runs\/\{"\{run_id\}"\}/);
  // No preview-modal pattern, no placeholder banner from ZIP
  assert.doesNotMatch(page, /Funcionalidade preservada/);
  assert.doesNotMatch(page, /módulo preservado/);
  assert.doesNotMatch(page, /PreviewActionModal/);
  assert.doesNotMatch(page, /PreviewPill/);
});

test("P7.4 experiments: planned controls keep disabled data-status='planned'", () => {
  assert.match(page, /data-status="planned"/);
  assert.match(page, /Exportar relatório/);
});

test("P7.4 CSS: summary/endpoint primitives still scoped to .evo-shell", () => {
  assert.match(css, /\.evo-shell \.evo-summary-row \{/);
  assert.match(css, /\.evo-shell \.evo-summary-card \{/);
  assert.match(css, /\.evo-shell \.evo-endpoint-list \{/);
  assert.match(css, /\.evo-shell \.evo-endpoint-row \{/);
  assert.doesNotMatch(css, /^\.evo-summary-row \{/m);
  assert.doesNotMatch(css, /^\.evo-endpoint-row \{/m);
});

test("P7.4 experiments: no preview bundle import or design ZIP mock leakage", () => {
  assert.doesNotMatch(page, /evalops-preview/);
  assert.doesNotMatch(page, /data\.jsx/);
  assert.doesNotMatch(page, /window\.MODULES/);
  assert.doesNotMatch(page, /evo-kpi-grid/);
});
