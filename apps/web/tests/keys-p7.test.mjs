import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const page = readFileSync(
  new URL("../app/o/[org]/p/[project]/keys/page.tsx", import.meta.url),
  "utf8",
);
const actions = readFileSync(
  new URL("../app/o/[org]/p/[project]/keys/ApiKeyActions.tsx", import.meta.url),
  "utf8",
);

test("keys: page keeps create flow, flash secret and authenticated key query", () => {
  assert.match(page, /createApiKeyAction/);
  assert.match(page, /getApiKeys\(resolved\.project_id\)/);
  assert.match(page, /consumeApiKeyFlash/);
  assert.match(page, /<ApiKeyActions/);
  assert.match(page, /name="project_id"/);
});

test("keys: header and table use system labels", () => {
  assert.match(page, /Chaves de API/);
  assert.match(page, /Situação/);
  assert.match(page, /Nome/);
  assert.match(page, /Prefixo/);
  assert.match(page, /Permissões/);
  assert.match(page, /Último uso/);
});

test("keys: counters and unavailable last-used data come from real payload", () => {
  assert.match(page, /keys\.filter\(\(key\) => !key\.revoked_at\)/);
  assert.match(page, /key\.revoked_at \?/);
  assert.match(page, /Sem dados/);
  assert.doesNotMatch(page, /avgScore/);
  assert.doesNotMatch(page, /errors_7d/);
  assert.doesNotMatch(page, /key\.expires_at/);
  assert.doesNotMatch(page, /last_used_at/);
});

test("keys: create form preserves required fields", () => {
  assert.match(page, /action=\{createApiKeyAction\}/);
  assert.match(page, /name="name"/);
  assert.match(page, /name="environment"/);
  assert.match(page, /name="scopes" value="ingest" defaultChecked/);
  assert.match(page, /name="scopes" value="read" defaultChecked/);
  assert.match(page, /name="scopes" value="evaluate"/);
  assert.doesNotMatch(page.match(/name="scopes" value="evaluate"[^>]*/)?.[0] ?? "", /defaultChecked/);
});

test("keys: revocation and deletion both require explicit confirmation", () => {
  assert.match(actions, /const action = revoked \? deleteApiKeyAction : revokeApiKeyAction/);
  assert.match(actions, /if \(!confirming\)/);
  assert.match(actions, /\{revoked \? "Excluir" : "Revogar"\}/);
  assert.match(actions, /action=\{action\}/);
  assert.match(actions, /name="key_id"/);
  assert.match(actions, /name="project_id"/);
  assert.match(actions, /Confirmar/);
  assert.match(actions, /Cancelar/);
});

test("keys: status, success and one-time secret states are visible", () => {
  assert.match(page, /qp\.created/);
  assert.match(page, /qp\.revoked/);
  assert.match(page, /qp\.deleted/);
  assert.match(page, /Chave revogada/);
  assert.match(page, /Chave excluída/);
  assert.match(page, /Chave criada\. Copie agora/);
  assert.match(page, /Este segredo não será mostrado de novo/);
  assert.match(page, /CopyTextButton/);
  assert.match(page, /badge--ok/);
  assert.match(page, /Revogada/);
  assert.match(page, /Ativa/);
});
