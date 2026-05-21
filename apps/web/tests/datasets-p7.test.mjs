import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const page = readFileSync(
  new URL("../app/o/[org]/p/[project]/datasets/page.tsx", import.meta.url),
  "utf8",
);
const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");

test("P7.3 datasets: page preserves server contract and real APIs", () => {
  assert.match(
    page,
    /import \{ addDatasetItemAction, buildDatasetFromTracesAction, createDatasetAction \}/,
  );
  assert.match(
    page,
    /import \{ getDatasetItems, getDatasets, hasAuthToken, resolveProject \}/,
  );
  assert.match(page, /await getDatasets\(resolved\.project_id\)/);
  assert.match(page, /await getDatasetItems\(dataset\.id\)/);
});

test("P7.3 datasets: header keeps eyebrow + subtitle from P5", () => {
  assert.match(page, /evo-page-header__eyebrow[^>]*>Dados · Datasets/);
  assert.match(page, /evo-page-header__title/);
  assert.match(page, /evo-page-header__subtitle/);
});

test("P7.3 datasets: summary row uses only real payload-derived values", () => {
  assert.match(page, /<section className="evo-summary-row"/);
  assert.match(page, /Datasets<\/p>/);
  assert.match(page, /\{rows\.length\.toLocaleString\("pt-BR"\)\}/);
  assert.match(page, /\{totalItems\.toLocaleString\("pt-BR"\)\}/);
  assert.match(page, /\{traceDatasets\.toLocaleString\("pt-BR"\)\}/);
  assert.match(page, /latestActivity \? relTime\(latestActivity\) : "—"/);
  // No invented metrics
  assert.doesNotMatch(page, /avgScore/);
  assert.doesNotMatch(page, /errors_7d/);
  assert.doesNotMatch(page, /attentionDot/);
});

test("P7.3 datasets: forms (create, add item, build-from-traces) preserved", () => {
  assert.match(page, /action=\{createDatasetAction\}/);
  assert.match(page, /action=\{addDatasetItemAction\}/);
  assert.match(page, /action=\{buildDatasetFromTracesAction\}/);
  assert.match(page, /name="slug"/);
  assert.match(page, /name="input_json"/);
  assert.match(page, /name="expected_output_json"/);
  assert.match(page, /name="metadata_json"/);
  assert.match(page, /name="dataset_id"/);
  assert.match(page, /name="project_id"/);
});

test("P7.3 datasets: tabs + table + item preview preserved", () => {
  assert.match(page, /<nav className="evo-tabs">/);
  assert.match(page, /Lista de datasets/);
  assert.match(page, /Previa de itens/);
  assert.match(page, /function statusForDataset\(/);
  assert.match(page, /function shortJson\(/);
});

test("P7.3 datasets: endpoints reference card is read-only (no modal preview)", () => {
  assert.match(page, /<h3 className="evo-card__title">Endpoints ativos<\/h3>/);
  assert.match(page, /aria-label="Endpoints do módulo Datasets"/);
  assert.match(page, /evo-endpoint-row__method--get/);
  assert.match(page, /evo-endpoint-row__method--post/);
  assert.match(page, /build-from-traces/);
  // No preview-modal pattern, no placeholder banner from ZIP
  assert.doesNotMatch(page, /Funcionalidade preservada/);
  assert.doesNotMatch(page, /módulo preservado/);
  assert.doesNotMatch(page, /PreviewActionModal/);
  assert.doesNotMatch(page, /PreviewPill/);
});

test("P7.3 datasets: planned Importar control keeps disabled data-status='planned'", () => {
  assert.match(page, /data-status="planned"/);
  assert.match(page, /Importar/);
});

test("P7.3 CSS: summary/endpoint primitives still scoped to .evo-shell", () => {
  assert.match(css, /\.evo-shell \.evo-summary-row \{/);
  assert.match(css, /\.evo-shell \.evo-summary-card \{/);
  assert.match(css, /\.evo-shell \.evo-endpoint-list \{/);
  assert.match(css, /\.evo-shell \.evo-endpoint-row \{/);
  assert.doesNotMatch(css, /^\.evo-summary-row \{/m);
  assert.doesNotMatch(css, /^\.evo-endpoint-row \{/m);
});

test("P7.3 datasets: no preview bundle import or design ZIP mock leakage", () => {
  assert.doesNotMatch(page, /evalops-preview/);
  assert.doesNotMatch(page, /data\.jsx/);
  assert.doesNotMatch(page, /window\.MODULES/);
  // Old kpi-grid replaced with summary-row
  assert.doesNotMatch(page, /evo-kpi-grid/);
});
