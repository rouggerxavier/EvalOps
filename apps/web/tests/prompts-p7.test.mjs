import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const page = readFileSync(
  new URL("../app/o/[org]/p/[project]/prompts/page.tsx", import.meta.url),
  "utf8",
);
const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");

test("P7.1 prompts: page preserves server contract and real APIs", () => {
  assert.match(page, /import \{ createPromptAction, createPromptVersionAction \}/);
  assert.match(page, /import \{ getPromptVersions, getPrompts, hasAuthToken, resolveProject \}/);
  assert.match(page, /await getPrompts\(resolved\.project_id\)/);
  assert.match(page, /await getPromptVersions\(p\.id\)/);
});

test("P7.1 prompts: header keeps eyebrow + subtitle from P5", () => {
  assert.match(page, /evo-page-header__eyebrow[^>]*>Operação · Prompts/);
  assert.match(page, /evo-page-header__title[^>]*>Prompts/);
  assert.match(page, /evo-page-header__subtitle/);
});

test("P7.1 prompts: summary row uses only real payload-derived values", () => {
  assert.match(page, /<section className="evo-summary-row"/);
  assert.match(page, /Prompts<\/p>/);
  assert.match(page, /\{totalPrompts\.toLocaleString\("pt-BR"\)\}/);
  assert.match(page, /\{totalVersions\.toLocaleString\("pt-BR"\)\}/);
  assert.match(page, /latestActivity \? relTime\(latestActivity\) : "—"/);
  // No invented metrics
  assert.doesNotMatch(page, /avgScore/);
  assert.doesNotMatch(page, /errors_7d/);
  assert.doesNotMatch(page, /attentionDot/);
});

test("P7.1 prompts: forms (create + new version) preserved", () => {
  assert.match(page, /action=\{createPromptAction\}/);
  assert.match(page, /action=\{createPromptVersionAction\}/);
  assert.match(page, /name="slug"/);
  assert.match(page, /name="template"/);
  assert.match(page, /name="variables_json"/);
  assert.match(page, /name="metadata_json"/);
  assert.match(page, /name="prompt_id"/);
});

test("P7.1 prompts: DiffView keeps both branches (first version + diff)", () => {
  assert.match(page, /function DiffView\(\{ current, previous \}/);
  assert.match(page, /if \(!previous\)/);
  assert.match(page, /const lines: Array<\{ text: string; kind: "add" \| "del" \| "same" \}>/);
});

test("P7.1 prompts: endpoints reference card is read-only (no modal preview)", () => {
  assert.match(page, /<h3 className="evo-card__title">Endpoints ativos<\/h3>/);
  assert.match(page, /aria-label="Endpoints do módulo Prompts"/);
  assert.match(page, /evo-endpoint-row__method--get/);
  assert.match(page, /evo-endpoint-row__method--post/);
  // No preview-modal pattern, no placeholder banner from ZIP
  assert.doesNotMatch(page, /Funcionalidade preservada/);
  assert.doesNotMatch(page, /módulo preservado/);
  assert.doesNotMatch(page, /PreviewActionModal/);
  assert.doesNotMatch(page, /PreviewPill/);
});

test("P7.1 prompts: planned controls keep disabled data-status='planned'", () => {
  assert.match(page, /data-status="planned"/);
  assert.match(page, /disabled/);
});

test("P7.1 CSS: summary/endpoint primitives scoped to .evo-shell", () => {
  assert.match(css, /\.evo-shell \.evo-summary-row \{/);
  assert.match(css, /\.evo-shell \.evo-summary-card \{/);
  assert.match(css, /\.evo-shell \.evo-summary-card__label/);
  assert.match(css, /\.evo-shell \.evo-summary-card__value/);
  assert.match(css, /\.evo-shell \.evo-endpoint-list \{/);
  assert.match(css, /\.evo-shell \.evo-endpoint-row \{/);
  // Never global
  assert.doesNotMatch(css, /^\.evo-summary-row \{/m);
  assert.doesNotMatch(css, /^\.evo-endpoint-row \{/m);
});

test("P7.1 prompts: no preview bundle import or design ZIP mock leakage", () => {
  assert.doesNotMatch(page, /evalops-preview/);
  assert.doesNotMatch(page, /data\.jsx/);
  assert.doesNotMatch(page, /window\.MODULES/);
});
