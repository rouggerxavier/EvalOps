import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "node:fs";
import { loadTs } from "./helpers/load-ts.mjs";

const redirect = (path) => { throw Object.assign(new Error(path), { redirect: true }); };
const form = (values = {}) => {
  const data = new FormData();
  for (const [name, value] of Object.entries({ current_password: "current-secret", new_password: "new-secret-123", confirm_password: "new-secret-123", ...values })) data.set(name, value);
  return data;
};
const nextLink = ({ children, ...props }) => React.createElement("a", props, children);
function actions({ token = "cookie-token", failure } = {}) {
  const calls = [];
  class AuthError extends Error { constructor(status) { super("private backend detail"); this.status = status; } }
  return { calls, ...loadTs("lib/auth-actions.ts", {
    "next/navigation": { redirect },
    "./auth": {
      AuthError, getSessionCookieToken: async () => token,
      clearSessionCookie: async () => calls.push(["clear"]),
      changePasswordWithApi: async (...args) => {
        calls.push(["change", ...args]);
        if (failure) throw failure === "network" ? new Error("private DB secret") : new AuthError(failure);
      },
    },
  }) };
}
const destination = (path) => (error) => error.redirect && error.message === path;

test("password change sends only cookie authority and passwords, then clears and requires login", async () => {
  const h = actions();
  await assert.rejects(h.changePasswordAction(form({ user_id: "attacker-chosen", email: "other@example.com" })), destination("/login?password_changed=1"));
  assert.deepEqual(h.calls, [["change", "cookie-token", { current_password: "current-secret", new_password: "new-secret-123" }], ["clear"]]);
});

test("missing session never changes credentials", async () => {
  const h = actions({ token: null });
  await assert.rejects(h.changePasswordAction(form()), destination("/login"));
  assert.deepEqual(h.calls, []);
});

test("invalid fields and mismatch never reach API or expose passwords in redirects", async () => {
  for (const [fields, reason] of [
    [{ current_password: "" }, "invalid_password"], [{ current_password: "x".repeat(257) }, "invalid_password"],
    [{ new_password: "short" }, "invalid_password"], [{ new_password: "x".repeat(257) }, "invalid_password"],
    [{ confirm_password: "different-secret" }, "password_mismatch"],
  ]) {
    const h = actions();
    await assert.rejects(h.changePasswordAction(form(fields)), destination(`/account?error=${reason}`));
    assert.deepEqual(h.calls, []);
  }
});

test("API failures have fixed safe copy; expired sessions clear cookies", async () => {
  for (const [failure, path] of [[400, "/account?error=invalid_current_password"], [422, "/account?error=invalid_password"], [429, "/account?error=too_many_attempts"], [500, "/account?error=unavailable"], ["network", "/account?error=unavailable"], [401, "/login?session_expired=1"]]) {
    const h = actions({ failure });
    await assert.rejects(h.changePasswordAction(form()), destination(path));
    assert.equal(h.calls.some(([kind]) => kind === "clear"), failure === 401);
  }
});

test("real auth helper sends bearer JSON POST, accepts 204 and clears private cookie", async (t) => {
  const writes = [], calls = [];
  t.mock.method(globalThis, "fetch", async (...args) => { calls.push(args); return new Response(null, { status: 204 }); });
  const auth = loadTs("lib/auth.ts", {
    "next/headers": { cookies: async () => ({ get: () => undefined, set: (value) => writes.push(value) }) },
    "./config": { getApiBaseUrl: () => "http://api.example/v1", isDevMode: () => true },
  });
  assert.equal(await auth.getSession(), null);
  assert.deepEqual(calls, []);
  await auth.changePasswordWithApi("cookie-token", { current_password: "old", new_password: "new" });
  assert.equal(calls[0][0], "http://api.example/v1/auth/change-password");
  assert.equal(calls[0][1].method, "POST");
  assert.equal(calls[0][1].headers.Authorization, "Bearer cookie-token");
  assert.deepEqual(JSON.parse(calls[0][1].body), { current_password: "old", new_password: "new" });
  assert.equal(calls[0][1].cache, "no-store");
  await auth.clearSessionCookie();
  assert.equal(writes[0].maxAge, 0);
  assert.equal(writes[0].httpOnly, true);
});

function page(session) {
  return loadTs("app/account/page.tsx", {
    "next/link": nextLink, "next/navigation": { redirect },
    "@/lib/auth": { getSession: async () => session },
    "@/lib/auth-actions": { changePasswordAction: "/change-test", logoutAction: "/logout-test" },
    "@/components/ChangePasswordSubmit": { ChangePasswordSubmit: () => React.createElement("button", { type: "submit" }, "Trocar senha e sair") },
  }).default;
}

test("account requires a real session and renders labeled private fields with safe errors", async () => {
  await assert.rejects(page(null)({ searchParams: Promise.resolve({}) }), destination("/login"));
  const html = renderToStaticMarkup(await page({ user: { email: "user@example.com" } })({ searchParams: Promise.resolve({ error: "invalid_current_password" }) }));
  assert.equal((html.match(/type="password"/g) ?? []).length, 3);
  for (const name of ["current_password", "new_password", "confirm_password"]) assert.match(html, new RegExp(`name="${name}"`));
  assert.match(html, /autoComplete="current-password"/i);
  assert.match(html, /autoComplete="new-password"/i);
  assert.match(html, /8 a 256 caracteres/);
  assert.match(html, /todas as suas sessões serão encerradas/);
  assert.match(html, /role="alert"/);
  assert.match(html, /Senha atual incorreta/);
  const untrusted = renderToStaticMarkup(await page({ user: { email: "user@example.com" } })({ searchParams: Promise.resolve({ error: "private backend secret" }) }));
  assert.doesNotMatch(untrusted, /private backend secret/);
});

test("active topbar exposes Conta while retaining logout", () => {
  const { EvoTopbar } = loadTs("components/EvoTopbar.tsx", {
    "next/link": nextLink,
    "next/navigation": { usePathname: () => "/o/org/p/project", useSearchParams: () => new URLSearchParams() },
    "@/lib/actions": { setEnvironmentAction: "/env" }, "@/lib/auth-actions": { logoutAction: "/logout" },
    "@/components/ui/NotificationsBell": { NotificationsBell: () => null },
  });
  const html = renderToStaticMarkup(React.createElement(EvoTopbar, { org: "org", project: "project", orgLabel: "Org", projectLabel: "Project", initials: "AC", mobileMenuOpen: false, onMenuToggle: () => {} }));
  assert.match(html, /href="\/account"[^>]*>Conta<\/a>/);
  assert.match(html, /action="\/logout"/);
  assert.match(html, /aria-label="Sair"/);
  const src = readFileSync(new URL("../components/ChangePasswordSubmit.tsx", import.meta.url), "utf8");
  assert.match(src, /useFormStatus/);
  assert.match(src, /disabled=\{pending\}/);
});


test("adversarial query keys render the generic fallback without inherited object properties", async () => {
  for (const error of ["__proto__", "constructor", "toString", "hasOwnProperty", "unknown"] ) {
    const html = renderToStaticMarkup(await page({ user: { email: "user@example.com" } })({ searchParams: Promise.resolve({ error }) }));
    assert.match(html, /Não foi possível confirmar a troca/);
    assert.match(html, /role="alert"/);
    assert.doesNotMatch(html, /Object|function|\[object/);
  }
});


test("Unicode password lengths use code points and preserve current/new values intact", async () => {
  const current = "😀".repeat(200);
  for (const count of [8, 256]) {
    const password = "😀".repeat(count);
    const h = actions();
    await assert.rejects(h.changePasswordAction(form({ current_password: current, new_password: password, confirm_password: password })), destination("/login?password_changed=1"));
    assert.deepEqual(h.calls[0], ["change", "cookie-token", { current_password: current, new_password: password }]);
  }
  const h = actions();
  const tooLong = "😀".repeat(257);
  await assert.rejects(h.changePasswordAction(form({ new_password: tooLong, confirm_password: tooLong })), destination("/account?error=invalid_password"));
  assert.deepEqual(h.calls, []);
});

test("password fields retain Unicode contract and associate relevant validation errors", async () => {
  for (const error of ["invalid_current_password", "password_mismatch", "invalid_password"]) {
    const html = renderToStaticMarkup(await page({ user: { email: "user@example.com" } })({ searchParams: Promise.resolve({ error }) }));
    assert.doesNotMatch(html, /minLength|maxLength/i);
    assert.match(html, /id="password-error"/);
    assert.match(html, /aria-invalid="true"/);
    assert.match(html, /aria-describedby="[^"]*password-error/);
  }
});
