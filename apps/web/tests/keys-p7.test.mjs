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
  // Bug 3.1: assert the *structural* binding — Revogar inside the !revoked_at
  // branch and Excluir inside the revoked branch of the same ternary. A
  // regression that inverts the two forms must fail this test, not pass
  // because both strings appear somewhere on the page.
  //
  // A naive `\([\s\S]*?\)` capture is unsafe because JSX style values like
  // `color: "var(--err)"` introduce inner `)` that stop the lazy capture too
  // early. Anchor instead on the `</form>` terminator that both branches end
  // with — there is exactly one `</form>` per branch in the JSX ternary.
  const ternaryMatch = page.match(
    /!key\.revoked_at \? \(\s*([\s\S]*?<\/form>)\s*\)\s*:\s*\(\s*([\s\S]*?<\/form>)\s*\)/,
  );
  assert.ok(ternaryMatch, "ternary on !key.revoked_at not found in row actions");
  const [, activeBranch, revokedBranch] = ternaryMatch;

  // Active branch must wire revokeApiKeyAction and render the Revogar button,
  // and must NOT contain delete-related affordances.
  assert.match(activeBranch, /action=\{revokeApiKeyAction\}/);
  assert.match(activeBranch, /\bRevogar\b/);
  assert.doesNotMatch(activeBranch, /deleteApiKeyAction/);
  assert.doesNotMatch(activeBranch, /\bExcluir\b/);

  // Revoked branch must wire deleteApiKeyAction and render the danger-coloured
  // Excluir button, and must NOT expose the Revogar action.
  assert.match(revokedBranch, /action=\{deleteApiKeyAction\}/);
  assert.match(revokedBranch, /\bExcluir\b/);
  assert.match(revokedBranch, /color: "var\(--err\)"/);
  assert.doesNotMatch(revokedBranch, /revokeApiKeyAction/);
  assert.doesNotMatch(revokedBranch, /\bRevogar\b/);

  // Both forms must carry project_id and key_id so the action can dispatch.
  assert.match(activeBranch, /name="key_id"/);
  assert.match(activeBranch, /name="project_id"/);
  assert.match(revokedBranch, /name="key_id"/);
  assert.match(revokedBranch, /name="project_id"/);
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
