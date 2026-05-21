import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const page = readFileSync(
  new URL("../app/o/[org]/p/[project]/keys/page.tsx", import.meta.url),
  "utf8",
);
const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");

test("P7.5 keys: page preserves server contract and real APIs", () => {
  assert.match(page, /import \{ createApiKeyAction, revokeApiKeyAction \}/);
  assert.match(page, /import \{ getApiKeys, hasAuthToken, resolveProject \}/);
  assert.match(page, /await getApiKeys\(resolved\.project_id\)/);
  assert.match(page, /import \{ consumeApiKeyFlash \}/);
});

test("P7.5 keys: header keeps eyebrow + subtitle from P5", () => {
  assert.match(page, /evo-page-header__eyebrow[^>]*>Acesso · Chaves API/);
  assert.match(page, /evo-page-header__title[^>]*>Chaves API/);
  assert.match(page, /evo-page-header__subtitle/);
});

test("P7.5 keys: summary row uses only real payload-derived values", () => {
  assert.match(page, /<section className="evo-summary-row"/);
  assert.match(page, /Chaves<\/p>/);
  assert.match(page, /Ativas<\/p>/);
  assert.match(page, /Revogadas<\/p>/);
  assert.match(page, /\{keys\.length\.toLocaleString\("pt-BR"\)\}/);
  assert.match(page, /\{activeCount\.toLocaleString\("pt-BR"\)\}/);
  assert.match(page, /\{revokedCount\.toLocaleString\("pt-BR"\)\}/);
  assert.match(page, /latestActivity \? relTime\(latestActivity\) : "—"/);
  // No invented metrics
  assert.doesNotMatch(page, /avgScore/);
  assert.doesNotMatch(page, /errors_7d/);
  assert.doesNotMatch(page, /attentionDot/);
  // Não criar dot/badge baseado em expires_at (campo ausente no tipo ApiKey)
  assert.doesNotMatch(page, /key\.expires_at/);
});

test("P7.5 keys: forms (create + revoke) preserved with required fields", () => {
  assert.match(page, /action=\{createApiKeyAction\}/);
  assert.match(page, /action=\{revokeApiKeyAction\}/);
  assert.match(page, /name="name"/);
  assert.match(page, /name="environment"/);
  assert.match(page, /name="scopes"/);
  assert.match(page, /name="key_id"/);
  assert.match(page, /name="project_id"/);
});

test("P7.5 keys: security banner política + flash secret card preserved", () => {
  assert.match(page, /Política de chaves/);
  assert.match(page, /rotacione a cada 90 dias/);
  assert.match(page, /Nova chave criada/);
  assert.match(page, /Segredo exibido apenas nesta resposta/);
  assert.match(page, /CopyTextButton/);
  assert.match(page, /maskPrefix/);
});

test("P7.5 keys: status badge + revoke inline action preserved", () => {
  assert.match(page, /function statusBadge\(revokedAt: string \| null\)/);
  assert.match(page, /evo-badge--err/);
  assert.match(page, /evo-badge--ok/);
  assert.match(page, /revogada/);
  assert.match(page, /ativa/);
});

test("P7.5 keys: endpoints reference card is read-only (no modal preview)", () => {
  assert.match(page, /<h3 className="evo-card__title">Endpoints ativos<\/h3>/);
  assert.match(page, /aria-label="Endpoints do módulo Chaves API"/);
  assert.match(page, /evo-endpoint-row__method--get/);
  assert.match(page, /evo-endpoint-row__method--post/);
  assert.match(page, /\/api-keys\/\{"\{key_id\}"\}\/revoke/);
  // No preview-modal pattern, no placeholder banner from ZIP
  assert.doesNotMatch(page, /Funcionalidade preservada/);
  assert.doesNotMatch(page, /módulo preservado/);
  assert.doesNotMatch(page, /PreviewActionModal/);
  assert.doesNotMatch(page, /PreviewPill/);
});

test("P7.5 CSS: summary/endpoint primitives still scoped to .evo-shell", () => {
  assert.match(css, /\.evo-shell \.evo-summary-row \{/);
  assert.match(css, /\.evo-shell \.evo-summary-card \{/);
  assert.match(css, /\.evo-shell \.evo-endpoint-list \{/);
  assert.match(css, /\.evo-shell \.evo-endpoint-row \{/);
  assert.doesNotMatch(css, /^\.evo-summary-row \{/m);
  assert.doesNotMatch(css, /^\.evo-endpoint-row \{/m);
});

test("P7.5 keys: no preview bundle import, no ZIP mock leakage, no kpi-grid", () => {
  assert.doesNotMatch(page, /evalops-preview/);
  assert.doesNotMatch(page, /data\.jsx/);
  assert.doesNotMatch(page, /window\.MODULES/);
  assert.doesNotMatch(page, /evo-kpi-grid/);
});
