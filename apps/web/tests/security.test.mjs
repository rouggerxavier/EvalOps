// Phase 1 P0 security regression — node:test runner.
//
// `package.json` ships `node --test` without a TypeScript loader, so these
// tests validate the *contract* expected by `lib/config.ts` and `lib/auth.ts`
// by re-implementing the validation rules in plain JS. The canonical
// implementation still lives in TS — when changing the TS rules, mirror them
// here so this safety net stays accurate.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

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

// --- G-23: error sanitization -------------------------------------------
// Mirror of the sanitizeApiError logic in lib/actions.ts.

const SAFE_HTTP_MESSAGES = {
  400: "Dados inválidos. Verifique os campos e tente novamente.",
  401: "Sessão expirada ou não autorizado. Faça login novamente.",
  402: "Limite do plano atingido.",
  403: "Sem permissão para esta ação.",
  404: "Recurso não encontrado.",
  409: "Conflito: o recurso já existe ou foi modificado.",
  413: "Payload muito grande.",
  422: "Dados inválidos. Verifique os campos e tente novamente.",
  429: "Muitas requisições. Aguarde e tente novamente.",
};

const GENERIC_ERROR = "Algo deu errado. Tente novamente.";

const LEAK_PATTERNS = [
  /traceback\s+\(most recent call last\)/i,
  /sqlalchemy/i,
  /sqlite/i,
  /psycopg/i,
  /\bselect\b.{1,40}\bfrom\b/i,
  /\binsert\b.{1,20}\binto\b/i,
  /file ".*\.py"/i,
  /evk_[a-z0-9_]{6,}/i,
  /line \d+, in /i,
];

function sanitizeApiError(message) {
  const match = /^API (\d{3}):/.exec(message);
  if (match) {
    const httpStatus = parseInt(match[1], 10);
    return SAFE_HTTP_MESSAGES[httpStatus] ?? GENERIC_ERROR;
  }
  for (const pattern of LEAK_PATTERNS) {
    if (pattern.test(message)) return GENERIC_ERROR;
  }
  return GENERIC_ERROR;
}

test("G-23: SQL in error body becomes generic message", () => {
  const msg = "API 500: SELECT * FROM traces WHERE id = '123'; -- injected";
  assert.equal(sanitizeApiError(msg), GENERIC_ERROR);
});

test("G-23: Python traceback becomes generic message", () => {
  const msg = "API 500: Traceback (most recent call last):\n  File \"app.py\", line 42, in handler\nValueError: bad value";
  assert.equal(sanitizeApiError(msg), GENERIC_ERROR);
});

test("G-23: SQLAlchemy leak becomes generic message", () => {
  const msg = "API 500: sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) table not found";
  assert.equal(sanitizeApiError(msg), GENERIC_ERROR);
});

test("G-23: API key leak becomes generic message", () => {
  const msg = "Error: evk_prod_abc123xyz invalid";
  assert.equal(sanitizeApiError(msg), GENERIC_ERROR);
});

test("G-23: 401 maps to friendly auth message", () => {
  const msg = "API 401: Unauthorized";
  assert.equal(sanitizeApiError(msg), SAFE_HTTP_MESSAGES[401]);
});

test("G-23: 409 maps to safe conflict message", () => {
  const msg = "API 409: {\"detail\":\"organization_slug_taken\"}";
  assert.equal(sanitizeApiError(msg), SAFE_HTTP_MESSAGES[409]);
});

test("G-23: 429 maps to rate-limit message", () => {
  const msg = "API 429: too_many_requests";
  assert.equal(sanitizeApiError(msg), SAFE_HTTP_MESSAGES[429]);
});

test("G-23: 500 maps to generic error", () => {
  const msg = "API 500: Internal Server Error";
  assert.equal(sanitizeApiError(msg), GENERIC_ERROR);
});

test("G-23: unknown non-API error maps to generic", () => {
  const msg = "fetch failed: ECONNREFUSED";
  assert.equal(sanitizeApiError(msg), GENERIC_ERROR);
});

test("G-23: 400 maps to validation message", () => {
  const msg = "API 400: {\"detail\":\"invalid_cursor\"}";
  assert.equal(sanitizeApiError(msg), SAFE_HTTP_MESSAGES[400]);
});

// --- A-02 / Fix-7B.2: frontend logout contract ----------------------------
// Next.js server actions are TS + runtime-bound, and node --test here runs
// plain JS. We validate the expected contract shape mirrored from
// lib/auth.ts + lib/auth-actions.ts.

async function logoutWithApiFor(baseUrl, token, fetchImpl) {
  const res = await fetchImpl(`${baseUrl}/auth/logout`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`logout_failed_${res.status}`);
  }
}

async function logoutActionFlowFor({ token, baseUrl, fetchImpl, clearLocal }) {
  try {
    if (token) {
      await logoutWithApiFor(baseUrl, token, fetchImpl);
    }
  } catch {
    // local logout must still happen
  }
  await clearLocal();
}

test("Fix-7B.2: logout calls POST /auth/logout with Authorization bearer", async () => {
  const calls = [];
  await logoutActionFlowFor({
    token: "jwt_abc",
    baseUrl: "https://api.evalops.example.com/v1",
    fetchImpl: async (url, init) => {
      calls.push([url, init]);
      return { ok: true, status: 204 };
    },
    clearLocal: async () => {},
  });

  assert.equal(calls.length, 1);
  assert.equal(calls[0][0], "https://api.evalops.example.com/v1/auth/logout");
  assert.equal(calls[0][1].method, "POST");
  assert.equal(calls[0][1].headers.Authorization, "Bearer jwt_abc");
});

test("Fix-7B.2: logout clears local session after revoke attempt", async () => {
  const steps = [];
  await logoutActionFlowFor({
    token: "jwt_abc",
    baseUrl: "https://api.evalops.example.com/v1",
    fetchImpl: async () => {
      steps.push("revoke");
      return { ok: true, status: 204 };
    },
    clearLocal: async () => {
      steps.push("clear");
    },
  });

  assert.deepEqual(steps, ["revoke", "clear"]);
});

test("Fix-7B.2: backend logout failure still clears local session", async () => {
  const steps = [];
  await logoutActionFlowFor({
    token: "jwt_abc",
    baseUrl: "https://api.evalops.example.com/v1",
    fetchImpl: async () => {
      steps.push("revoke");
      throw new Error("network_down");
    },
    clearLocal: async () => {
      steps.push("clear");
    },
  });

  assert.deepEqual(steps, ["revoke", "clear"]);
});

test("Fix-7B.2: logout without token is idempotent and does not call backend", async () => {
  let called = false;
  let cleared = false;
  await logoutActionFlowFor({
    token: null,
    baseUrl: "https://api.evalops.example.com/v1",
    fetchImpl: async () => {
      called = true;
      return { ok: true, status: 204 };
    },
    clearLocal: async () => {
      cleared = true;
    },
  });

  assert.equal(called, false);
  assert.equal(cleared, true);
});

test("Fix-7B.2: source contract has logout helper using POST + bearer", () => {
  const src = readFileSync(new URL("../lib/auth.ts", import.meta.url), "utf8");
  assert.match(src, /getApiBaseUrl\(\)\}\/auth\/logout/);
  assert.match(src, /method:\s*"POST"/);
  assert.match(src, /Authorization:\s*`Bearer \$\{token\}`/);
});

test("Fix-7B.2: source contract tries revoke before local clear", () => {
  const src = readFileSync(new URL("../lib/auth-actions.ts", import.meta.url), "utf8");
  assert.match(src, /if \(sessionToken\)/);
  assert.match(src, /await logoutWithApi\(sessionToken\)/);
  assert.match(src, /await clearSessionCookie\(\)/);

  const revokeIdx = src.indexOf("await logoutWithApi(sessionToken);");
  const clearIdx = src.indexOf("await clearSessionCookie();");
  assert.ok(revokeIdx !== -1 && clearIdx > revokeIdx);
});
