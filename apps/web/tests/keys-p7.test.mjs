import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const page = readFileSync(
  new URL("../app/o/[org]/p/[project]/keys/page.tsx", import.meta.url),
  "utf8",
);

test("keys: page imports real server actions including delete", () => {
  assert.match(page, /createApiKeyAction/);
  assert.match(page, /revokeApiKeyAction/);
  assert.match(page, /deleteApiKeyAction/);
  assert.match(page, /import \{ getApiKeys, hasAuthToken, resolveProject \}/);
  assert.match(page, /await getApiKeys\(resolved\.project_id\)/);
  assert.match(page, /import \{ consumeApiKeyFlash \}/);
});

test("keys: header keeps eyebrow + subtitle", () => {
  assert.match(page, /page-header__eyebrow[^>]*>Acesso · Chaves API/);
  assert.match(page, /page-header__title[^>]*>Chaves API/);
  assert.match(page, /page-header__subtitle/);
});

test("keys: summary row uses only real payload-derived values", () => {
  assert.match(page, /<section className="module-summary"/);
  assert.match(page, /Chaves<\/p>/);
  assert.match(page, /Ativas<\/p>/);
  assert.match(page, /Revogadas<\/p>/);
  assert.match(page, /\{keys\.length\.toLocaleString\("pt-BR"\)\}/);
  assert.match(page, /\{activeCount\.toLocaleString\("pt-BR"\)\}/);
  assert.match(page, /\{revokedCount\.toLocaleString\("pt-BR"\)\}/);
  assert.match(page, /latestActivity \? relTime\(latestActivity\) : "—"/);
  // No invented metrics or fields absent from the ApiKey type.
  assert.doesNotMatch(page, /avgScore/);
  assert.doesNotMatch(page, /errors_7d/);
  assert.doesNotMatch(page, /key\.expires_at/);
});

test("keys: create form preserves required hidden + visible fields", () => {
  assert.match(page, /action=\{createApiKeyAction\}/);
  assert.match(page, /name="name"/);
  assert.match(page, /name="environment"/);
  assert.match(page, /name="scopes"/);
});

test("keys: row actions render Revogar for active and Excluir for revoked", () => {
  // Revoke form gated by !key.revoked_at.
  assert.match(page, /!key\.revoked_at \?[\s\S]*?action=\{revokeApiKeyAction\}/);
  assert.match(page, /action=\{revokeApiKeyAction\}/);
  assert.match(page, /\bRevogar\b/);
  // Delete form gated by the revoked branch with the danger-coloured button.
  assert.match(page, /action=\{deleteApiKeyAction\}/);
  assert.match(page, /\bExcluir\b/);
  assert.match(page, /color: "var\(--err\)"/);
  // Both forms must carry project_id and key_id so the action can dispatch.
  assert.match(page, /name="key_id"/);
  assert.match(page, /name="project_id"/);
});

test("keys: success/error alerts cover created, revoked and deleted", () => {
  assert.match(page, /qp\.created/);
  assert.match(page, /qp\.revoked/);
  assert.match(page, /qp\.deleted/);
  assert.match(page, /Chave API excluída com sucesso/);
});

test("keys: security banner + flash secret card preserved", () => {
  assert.match(page, /Política de chaves/);
  assert.match(page, /rotacione a cada 90 dias/);
  assert.match(page, /Nova chave criada/);
  assert.match(page, /Segredo exibido apenas nesta resposta/);
  assert.match(page, /CopyTextButton/);
  assert.match(page, /maskPrefix/);
});

test("keys: status badge function still reports ativa/revogada", () => {
  assert.match(page, /function statusBadge\(revokedAt: string \| null\)/);
  assert.match(page, /badge badge--err/);
  assert.match(page, /badge badge--ok/);
  assert.match(page, /\brevogada\b/);
  assert.match(page, /\bativa\b/);
});
