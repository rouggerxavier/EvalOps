import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { loadTs } from "./helpers/load-ts.mjs";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

function harness(failure) {
  const calls = [];
  class AuthError extends Error { constructor(status) { super("private backend detail"); this.status = status; } }
  return { calls, ...loadTs("lib/recovery-actions.ts", {
    "next/navigation": { redirect: (path) => { throw Object.assign(new Error(path), { redirect: true }); } },
    "./auth": { AuthError, clearSessionCookie: async () => calls.push(["clear"]), recoverPasswordWithApi: async (...args) => {
      calls.push(args);
      if (failure) throw failure === "network" ? new Error("private SMTP password") : new AuthError(failure);
    } },
  }) };
}
function form(values = {}) {
  const result = new FormData();
  for (const [key, value] of Object.entries({ token: "a".repeat(43), email: "Account@Example.COM", new_password: "new-password", confirm_password: "new-password", ...values })) result.set(key, value);
  return result;
}

test("forgot normalizes email and fixed acknowledgement, never echoes", async () => {
  const h = harness();
  assert.deepEqual(await h.forgotPasswordAction({}, form()), { sent: true });
  assert.deepEqual(h.calls, [["forgot-password", { email: "account@example.com" }]]);
  assert.deepEqual(await h.forgotPasswordAction({}, form({ email: "bad" })), { error: "invalid_email" });
});

test("reset validates codepoints, mismatch, then clears and requires new login", async () => {
  for (const count of [8, 256]) {
    const h = harness(), password = "😀".repeat(count);
    await assert.rejects(h.resetPasswordAction(form({ new_password: password, confirm_password: password })), (e) => e.redirect && e.message === "/login?password_changed=1");
    assert.deepEqual(h.calls, [["reset-password", { token: "a".repeat(43), new_password: password }], ["clear"]]);
  }
  for (const [values, error] of [[{ token: "bad" }, "invalid_reset"], [{ new_password: "😀".repeat(257) }, "invalid_password"], [{ new_password: "short" }, "invalid_password"], [{ confirm_password: "different" }, "password_mismatch"]]) {
    const h = harness();
    assert.deepEqual(await h.resetPasswordAction(form(values)), { error });
    assert.deepEqual(h.calls, []);
  }
});

test("backend errors become safe fixed codes", async () => {
  for (const [status, code] of [[400, "invalid_reset"], [422, "invalid_password"], [429, "too_many_attempts"], [503, "unavailable"], ["network", "unavailable"]]) {
    assert.deepEqual(await harness(status).resetPasswordAction(form()), { error: code });
    assert.deepEqual(await harness(status).forgotPasswordAction({}, form()), { error: status === 429 ? "too_many_attempts" : "unavailable" });
  }
});

test("fragment is removed including query, without persistent token storage", () => {
  const { takeRecoveryFragment } = loadTs("lib/recovery-fragment.ts");
  const calls = [], history = { state: {}, replaceState: (...args) => calls.push(args) };
  assert.equal(takeRecoveryFragment({ hash: "#" + "a".repeat(43), pathname: "/reset-password" }, history), "a".repeat(43));
  assert.deepEqual(calls, [[history.state, "", "/reset-password"]]);
  assert.equal(takeRecoveryFragment({ hash: "#bad", pathname: "/reset-password" }, history), "");
  const source = readFileSync(new URL("../components/RecoveryForms.tsx", import.meta.url), "utf8");
  assert.match(source, /if \(token\.current === null\) token\.current = takeRecoveryFragment/);
  assert.doesNotMatch(source, /localStorage|sessionStorage|document\.cookie|type="hidden"|name="token"/);
  assert.match(source, /aria-busy=\{pending\}/);
});

test("API transport is body-only POST without bearer", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", async (...args) => { calls.push(args); return new Response(null, { status: 204 }); });
  const auth = loadTs("lib/auth.ts", { "next/headers": {}, "./config": { getApiBaseUrl: () => "http://api.example/v1", isDevMode: () => false } });
  await auth.recoverPasswordWithApi("reset-password", { token: "a".repeat(43), new_password: "secret" });
  assert.equal(calls[0][0], "http://api.example/v1/auth/reset-password");
  assert.deepEqual(calls[0][1].headers, { "Content-Type": "application/json" });
  assert.equal(calls[0][1].method, "POST");
  assert.deepEqual(JSON.parse(calls[0][1].body), { token: "a".repeat(43), new_password: "secret" });
  assert.equal(calls[0][1].cache, "no-store");
});

test("pages ignore adversarial search errors and expose private metadata", () => {
  for (const [route, title] of [["forgot-password", "Recuperar senha"], ["reset-password", "Redefinir senha"]]) {
    const module = loadTs(`app/${route}/page.tsx`, { "@/components/RecoveryShell": { RecoveryShell: ({ title, children }) => React.createElement("main", null, title, children) }, "@/components/RecoveryForms": { ForgotPasswordForm: () => null, ResetPasswordForm: () => null } });
    assert.equal(module.metadata.referrer, "no-referrer");
    assert.equal(module.metadata.robots.index, false);
    for (const error of ["__proto__", "constructor", "toString", "private secret"]) {
      const html = renderToStaticMarkup(React.createElement(module.default, { searchParams: { error } }));
      assert.match(html, new RegExp(title));
      assert.doesNotMatch(html, /__proto__|Object|function|private secret/);
    }
  }
  assert.match(readFileSync(new URL("../app/login/page.tsx", import.meta.url), "utf8"), /href="\/forgot-password"/);
});
