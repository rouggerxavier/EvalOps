import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const page = readFileSync(
  new URL("../app/o/[org]/p/[project]/exports/page.tsx", import.meta.url),
  "utf8",
);
const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");

test("P7.6 exports: page preserves server contract and real APIs", () => {
  assert.match(page, /import \{ createExportAction \}/);
  assert.match(
    page,
    /getExport,\s*getExportDownloadPath,\s*getOrganizationSubscription,\s*getOrganizationUsage,\s*hasAuthToken,\s*resolveProject,/,
  );
  assert.match(page, /await getExport\(id\)/);
  assert.match(page, /getOrganizationUsage\(resolvedProject\.org_id\)/);
  assert.match(page, /getOrganizationSubscription\(resolvedProject\.org_id\)/);
});

test("P7.6 exports: header keeps eyebrow + subtitle from P5", () => {
  assert.match(page, /evo-page-header__eyebrow[^>]*>Dados · Exports/);
  assert.match(page, /evo-page-header__title[^>]*>Exports/);
  assert.match(page, /evo-page-header__subtitle/);
});

test("P7.6 exports: summary row uses only real payload-derived values", () => {
  assert.match(page, /<section className="evo-summary-row"/);
  assert.match(page, /Jobs conhecidos<\/p>/);
  assert.match(page, /Em andamento<\/p>/);
  assert.match(page, /Concluídos<\/p>/);
  assert.match(page, /\{exportRows\.length\.toLocaleString\("pt-BR"\)\}/);
  assert.match(page, /\{runningCount\.toLocaleString\("pt-BR"\)\}/);
  assert.match(page, /\{completedCount\.toLocaleString\("pt-BR"\)\}/);
  assert.match(page, /latestActivity \? relTime\(latestActivity\) : "—"/);
  // No invented metrics
  assert.doesNotMatch(page, /avgScore/);
  assert.doesNotMatch(page, /errors_7d/);
  assert.doesNotMatch(page, /attentionDot/);
});

test("P7.6 exports: create form preserved with required hidden fields", () => {
  assert.match(page, /action=\{createExportAction\}/);
  assert.match(page, /name="environment"/);
  assert.match(page, /name="status"/);
  assert.match(page, /name="name_contains"/);
  assert.match(page, /name="project_id"/);
  assert.match(page, /name="known_export_ids"/);
});

test("P7.6 exports: usage/quota panel preserved (Fix-7B.7)", () => {
  assert.match(page, /function UsageBar\(/);
  assert.match(page, /label="Traces"/);
  assert.match(page, /label="Avaliacoes"/);
  assert.match(page, /label="Exports"/);
  assert.match(page, /label="Spans"/);
  assert.match(page, /label="Tokens"/);
  assert.match(page, /Budget mensal de judge/);
  assert.match(page, /monthly_judge_budget_usd/);
});

test("P7.6 exports: authenticated download route preserved + sanitization", () => {
  assert.match(page, /getExportDownloadPath\(row\.job\.id, currentViewHref\)/);
  assert.match(page, /safeErrorMessage\(/);
  assert.match(page, /sanitizedQueryError/);
});

test("P7.6 exports: endpoints reference card is read-only (no modal preview)", () => {
  assert.match(page, /<h3 className="evo-card__title">Endpoints ativos<\/h3>/);
  assert.match(page, /aria-label="Endpoints do módulo Exports"/);
  assert.match(page, /evo-endpoint-row__method--get/);
  assert.match(page, /evo-endpoint-row__method--post/);
  assert.match(page, /\/exports\/\{"\{export_id\}"\}/);
  assert.match(page, /\/api\/exports\/\{"\{export_id\}"\}\/download/);
  // No preview-modal pattern, no placeholder banner from ZIP
  assert.doesNotMatch(page, /Funcionalidade preservada/);
  assert.doesNotMatch(page, /módulo preservado/);
  assert.doesNotMatch(page, /PreviewActionModal/);
  assert.doesNotMatch(page, /PreviewPill/);
});

test("P7.6 CSS: summary/endpoint primitives still scoped to .evo-shell", () => {
  assert.match(css, /\.evo-shell \.evo-summary-row \{/);
  assert.match(css, /\.evo-shell \.evo-summary-card \{/);
  assert.match(css, /\.evo-shell \.evo-endpoint-list \{/);
  assert.match(css, /\.evo-shell \.evo-endpoint-row \{/);
  assert.doesNotMatch(css, /^\.evo-summary-row \{/m);
  assert.doesNotMatch(css, /^\.evo-endpoint-row \{/m);
});

test("P7.6 exports: no preview bundle import, no ZIP mock leakage, no kpi-grid", () => {
  assert.doesNotMatch(page, /evalops-preview/);
  assert.doesNotMatch(page, /data\.jsx/);
  assert.doesNotMatch(page, /window\.MODULES/);
  assert.doesNotMatch(page, /evo-kpi-grid/);
});
