import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { loadTs } from "./helpers/load-ts.mjs";

const accepted = { organization_id: "org_id", organization_slug: "team", role: "viewer", permissions: ["read"], already_member: false };
function form(values) { const f = new FormData(); for (const [k, v] of Object.entries(values)) f.set(k, v); return f; }
function harness({ session = { token: "personal", user: { id: "self" } }, failure, acceptance = accepted, projects = [{ slug: "app" }] } = {}) {
  const calls = [], refreshed = [];
  return { calls, refreshed, ...loadTs("lib/membership-actions.ts", {
    "next/cache": { revalidatePath: (...args) => refreshed.push(args) },
    "./auth": { getSession: async () => session },
    "./api": { membershipRequest: async (...args) => {
      calls.push(args);
      if (failure) throw new Error(failure);
      return args[0] === "/invitations/accept" ? acceptance : { data: projects };
    }, getInvitations: async (...args) => { calls.push(args); return { data: [], next_cursor: null }; } },
  }) };
}
const ctx = { org: "team", project: "app", organization_id: "org_id" };

test("invitation issue normalizes email, validates raw CRLF and requires personal session", async () => {
  const h = harness();
  assert.ok((await h.manageMembershipAction(form({ ...ctx, operation: "invite", email: " Test@Example.com ", role: "viewer" }))).success);
  assert.deepEqual(h.calls, [["/organizations/org_id/invitations", "POST", { email: "test@example.com", role: "viewer" }]]);
  assert.deepEqual(h.refreshed, [["/o/team/p/app", "layout"]]);
  for (const values of [{ email: "test@example.com\r\n", role: "viewer" }, { email: "test@example.com", role: "owner" }]) {
    const h = harness();
    assert.ok((await h.manageMembershipAction(form({ ...ctx, operation: "invite", ...values }))).error);
    assert.deepEqual(h.calls, []);
  }
  const denied = harness({ session: null });
  assert.match((await denied.manageMembershipAction(form({ ...ctx, operation: "invite" }))).error, /conta pessoal/);
  assert.deepEqual(denied.calls, []);
});

test("remove and transfer require explicit confirmation; all membership changes refresh the layout", async () => {
  for (const operation of ["remove", "transfer", "role", "revoke"]) {
    const h = harness();
    const values = { ...ctx, operation, target: "self", role: "viewer" };
    if (["remove", "transfer"].includes(operation)) {
      assert.ok((await h.manageMembershipAction(form(values))).error);
      assert.deepEqual(h.calls, []);
    }
    const result = await h.manageMembershipAction(form({ ...values, confirmed: "yes" }));
    assert.ok(result.success);
    assert.equal(result.leave, operation === "remove");
    assert.equal(h.calls.length, 1);
    assert.deepEqual(h.refreshed, [["/o/team/p/app", "layout"]]);
  }
});

test("errors are fixed, actionable and do not echo backend data", async () => {
  for (const [error, pattern] of [["API 409: last_owner", /precisa manter um owner/], ["API 409: membership_conflict", /Atualize a lista/], ["API 409: already_member", /já pertence/], ["API 401: secret", /sessão/], ["API 403: secret", /permissão/], ["API 404: secret", /indisponível/], ["API 422: secret", /Confira/], ["API 429: secret", /Aguarde/], ["API 503: secret", /envio pode ter começado/]]) {
    const h = harness({ failure: error });
    const result = await h.manageMembershipAction(form({ ...ctx, operation: "invite", email: "ok@example.com", role: "viewer" }));
    assert.match(result.error, pattern); assert.doesNotMatch(result.error, /secret/); assert.deepEqual(h.refreshed, []);
  }
});

test("accept transports only a valid token on explicit POST and uses server permissions for project lookup", async () => {
  const h = harness();
  assert.ok((await h.acceptInvitationAction(form({ token: "bad" }))).error);
  assert.deepEqual(h.calls, []);
  const result = await h.acceptInvitationAction(form({ token: "a".repeat(43) }));
  assert.deepEqual(h.calls, [["/invitations/accept", "POST", { token: "a".repeat(43) }], ["/projects?organization_id=org_id"]]);
  assert.equal(result.href, "/o/team/p/app"); assert.ok(!JSON.stringify(result).includes("a".repeat(43)));
  const unknown = harness({ acceptance: { ...accepted, role: "legacy", permissions: [], already_member: true } });
  const restricted = await unknown.acceptInvitationAction(form({ token: "a".repeat(43) }));
  assert.equal(restricted.acceptance.role, "legacy"); assert.equal(restricted.href, undefined); assert.equal(unknown.calls.length, 1);
  assert.equal((await harness({ projects: [] }).acceptInvitationAction(form({ token: "a".repeat(43) }))).href, undefined);
  assert.match((await harness({ failure: "API 400: private" }).acceptInvitationAction(form({ token: "a".repeat(43) }))).error, /expirou ou já foi usado/);
  for (const failure of ["API 503: private", "API 500: private", "boom"]) {
    const error = (await harness({ failure }).acceptInvitationAction(form({ token: "a".repeat(43) }))).error;
    assert.match(error, /Abra o app para conferir se o acesso já existe/); assert.doesNotMatch(error, /envio|private/);
  }
  assert.match((await harness({ failure: "API 401: private" }).acceptInvitationAction(form({ token: "a".repeat(43) }))).error, /conta pessoal/);
});

test("personal membership transport never uses fallback and sanitizes HTTP errors", async (t) => {
  let session = null;
  const calls = [];
  let response = new Response(null, { status: 204 });
  t.mock.method(globalThis, "fetch", async (...args) => { calls.push(args); return response; });
  const api = loadTs("lib/api.ts", { react: { cache: (fn) => fn }, "./auth": { getSession: async () => session, getAuthToken: async () => "dev-fallback" }, "./config": { getApiBaseUrl: () => "http://localhost/v1" } });
  await assert.rejects(api.membershipRequest("/invitations/accept", "POST", { token: "a".repeat(43) }), /API 401/);
  assert.deepEqual(calls, []);
  session = { token: "fresh-personal" };
  await api.membershipRequest("/invitations/accept", "POST", { token: "a".repeat(43) });
  assert.equal(calls[0][1].headers.Authorization, "Bearer fresh-personal"); assert.equal(calls[0][1].cache, "no-store");
  response = new Response(JSON.stringify({ detail: "private-token-or-smtp" }), { status: 503 });
  await assert.rejects(api.membershipRequest("/invitations/accept", "POST"), /^Error: API 503: $/);
});

test("owner rows have no role form and unknown roles need an explicit choice", () => {
  const { MembershipManagement } = loadTs("app/o/[org]/p/[project]/settings/membership-management.tsx", {
    "next/navigation": { useRouter: () => ({ refresh() {}, replace() {} }) },
    "@/lib/membership-actions": { manageMembershipAction: async () => ({}), loadInvitationsAction: async () => ({}) },
    "./membership-management.module.css": {},
  });
  const member = (user_id, role) => ({ user_id, role, name: user_id, email: `${user_id}@example.invalid`, joined_at: "2026-11-09T12:00:00Z" });
  const html = renderToStaticMarkup(React.createElement(MembershipManagement, {
    org: "org", project: "project", organizationId: "org_id", currentUserId: "self", canAdmin: true, memberCursor: null, membersError: null,
    invitations: { data: [], next_cursor: null }, invitationsError: null,
    members: [member("self", "owner"), member("other-owner", "owner"), member("legacy", "legacy"), member("viewer", "viewer"), member("member", "member")],
  }));
  for (const owner of ["self", "other-owner"]) assert.doesNotMatch(html, new RegExp(`Novo papel de ${owner}@`));
  assert.equal(html.match(/Salvar papel/g).length, 3);
  const legacy = html.match(/<select[^>]*Novo papel de legacy@[^>]*>(.*?)<\/select>/)[0];
  assert.match(legacy, /required/);
  assert.match(legacy, /<option value="" disabled="" selected="">Manter papel atual \(legacy\)<\/option>/);
  assert.doesNotMatch(legacy, /value="(viewer|member)" selected/);
  assert.match(html.match(/<select[^>]*Novo papel de viewer@[^>]*>(.*?)<\/select>/)[0], /value="viewer" selected/);
  assert.match(html.match(/<select[^>]*Novo papel de member@[^>]*>(.*?)<\/select>/)[0], /value="member" selected/);
});
