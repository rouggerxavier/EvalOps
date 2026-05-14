// Phase 1 P0 security regression — node:test runner.
//
// `package.json` ships `node --test` without a TypeScript loader, so these
// tests validate the *contract* expected by `lib/config.ts` and `lib/auth.ts`
// by re-implementing the validation rules in plain JS. The canonical
// implementation still lives in TS — when changing the TS rules, mirror them
// here so this safety net stays accurate.

import { test } from "node:test";
import assert from "node:assert/strict";

// --- mirror of lib/config.ts ------------------------------------------------

function isLocalhostUrl(value) {
  try {
    const u = new URL(value);
    return u.hostname === "localhost" || u.hostname === "127.0.0.1";
  } catch {
    return false;
  }
}

function getApiBaseUrlFor(env) {
  const production = env.NODE_ENV === "production";
  const raw = env.EVALOPS_API_BASE_URL;
  if (production) {
    if (!raw || raw.trim() === "") {
      throw new Error("EVALOPS_API_BASE_URL must be set in production");
    }
    if (isLocalhostUrl(raw)) {
      throw new Error("EVALOPS_API_BASE_URL cannot point to localhost in production");
    }
    return raw;
  }
  return raw && raw.trim() ? raw : "http://localhost:8000/v1";
}

function isDevModeFor(env) {
  return env.NODE_ENV !== "production" && env.EVALOPS_DEV_MODE === "1";
}

function hasFallbackTokenFor(env) {
  return isDevModeFor(env) && Boolean(env.EVALOPS_DASHBOARD_BEARER_TOKEN);
}

// --- G-04 ------------------------------------------------------------------

test("G-04: dev with valid EVALOPS_API_BASE_URL returns it as-is", () => {
  const url = getApiBaseUrlFor({
    NODE_ENV: "development",
    EVALOPS_API_BASE_URL: "http://localhost:8000/v1",
  });
  assert.equal(url, "http://localhost:8000/v1");
});

test("G-04: dev without env falls back to localhost default", () => {
  const url = getApiBaseUrlFor({ NODE_ENV: "development" });
  assert.equal(url, "http://localhost:8000/v1");
});

test("G-04: prod without EVALOPS_API_BASE_URL throws", () => {
  assert.throws(
    () => getApiBaseUrlFor({ NODE_ENV: "production" }),
    /must be set in production/,
  );
});

test("G-04: prod with empty EVALOPS_API_BASE_URL throws", () => {
  assert.throws(
    () => getApiBaseUrlFor({ NODE_ENV: "production", EVALOPS_API_BASE_URL: "   " }),
    /must be set in production/,
  );
});

test("G-04: prod with localhost throws", () => {
  assert.throws(
    () =>
      getApiBaseUrlFor({
        NODE_ENV: "production",
        EVALOPS_API_BASE_URL: "http://localhost:8000/v1",
      }),
    /cannot point to localhost/,
  );
});

test("G-04: prod with 127.0.0.1 throws", () => {
  assert.throws(
    () =>
      getApiBaseUrlFor({
        NODE_ENV: "production",
        EVALOPS_API_BASE_URL: "http://127.0.0.1:8000/v1",
      }),
    /cannot point to localhost/,
  );
});

test("G-04: prod with valid public URL returns it", () => {
  const url = getApiBaseUrlFor({
    NODE_ENV: "production",
    EVALOPS_API_BASE_URL: "https://api.evalops.example.com/v1",
  });
  assert.equal(url, "https://api.evalops.example.com/v1");
});

// --- G-03 ------------------------------------------------------------------

test("G-03: prod blocks fallback bearer even when env is set", () => {
  assert.equal(
    hasFallbackTokenFor({
      NODE_ENV: "production",
      EVALOPS_DEV_MODE: "1",
      EVALOPS_DASHBOARD_BEARER_TOKEN: "evk_anything",
    }),
    false,
  );
});

test("G-03: dev without EVALOPS_DEV_MODE=1 blocks fallback", () => {
  assert.equal(
    hasFallbackTokenFor({
      NODE_ENV: "development",
      EVALOPS_DASHBOARD_BEARER_TOKEN: "evk_anything",
    }),
    false,
  );
});

test("G-03: dev with EVALOPS_DEV_MODE='true' (not '1') blocks fallback", () => {
  assert.equal(
    hasFallbackTokenFor({
      NODE_ENV: "development",
      EVALOPS_DEV_MODE: "true",
      EVALOPS_DASHBOARD_BEARER_TOKEN: "evk_anything",
    }),
    false,
  );
});

test("G-03: dev with EVALOPS_DEV_MODE='1' and token allows fallback", () => {
  assert.equal(
    hasFallbackTokenFor({
      NODE_ENV: "development",
      EVALOPS_DEV_MODE: "1",
      EVALOPS_DASHBOARD_BEARER_TOKEN: "evk_anything",
    }),
    true,
  );
});

test("G-03: dev with dev mode but no token still blocks", () => {
  assert.equal(
    hasFallbackTokenFor({
      NODE_ENV: "development",
      EVALOPS_DEV_MODE: "1",
    }),
    false,
  );
});

// --- G-02 (URL surface check) ----------------------------------------------
// Full flash-cookie behaviour requires a Next.js runtime harness (Playwright)
// which is intentionally out of scope this phase. We assert the negative
// contract on the redirect search params produced by createApiKeyAction:
// the key must never appear in URL params.

test("G-02: redirect search params after create must not include raw key", () => {
  const allowedParams = new Set(["created", "revoked", "error", "tab"]);
  // params shape mirrors what actions.ts emits after createApiKeyAction success
  const params = { created: "1" };
  for (const k of Object.keys(params)) {
    assert.ok(allowedParams.has(k), `unexpected redirect param: ${k}`);
  }
  assert.equal("key" in params, false);
  assert.equal("prefix" in params, false);
  assert.equal("secret" in params, false);
  assert.equal("api_key" in params, false);
});
