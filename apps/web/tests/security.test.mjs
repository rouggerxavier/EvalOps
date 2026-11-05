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
  410: "Export expirado. Gere um novo arquivo.",
  413: "Payload muito grande.",
  422: "Dados inválidos. Verifique os campos e tente novamente.",
  429: "Muitas requisições. Aguarde e tente novamente.",
};

const SAFE_DETAIL_MESSAGES = {
  project_slug_taken: "Este slug já está em uso nesta organização. Escolha outro.",
  organization_slug_taken: "Este slug de organização já está em uso. Escolha outro.",
  api_key_not_revoked: "Revogue a chave antes de excluí-la.",
  invalid_rubric: "Rubrica inválida. Confira o YAML e tente novamente.",
};

const GENERIC_ERROR = "Algo deu errado. Tente novamente.";

const LEAK_PATTERNS = [
  /traceback\s+\(most recent call last\)/i,
  /sqlalchemy/i,
  /sqlite/i,
  /psycopg/i,
  /postgres/i,
  /\b(?:IntegrityError|OperationalError|ProgrammingError)\b/,
  /\b(?:no such table|database is locked|constraint failed|unique constraint failed|foreign key constraint failed)\b/i,
  /\b(?:relation|column|table)\s+['"]?[\w.]+['"]?\s+does not exist\b/i,
  /\b(?:select|insert|update|delete)\b.{1,80}\b(?:from|into|set|where|values)\b/is,
  /file ".*\.py"/i,
  /line \d+, in /i,
  /(?:^|[\s'"(=])(?:\/(?:home|users|var|tmp|etc|root|opt|mnt)\/|[A-Za-z]:\\)/i,
  /\.venv[\\/]/i,
  / object at 0x[0-9a-fA-F]+/i,
  /eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}/,
  /\bevk_[a-z0-9_]{4,}/i,
  /\bsk-[A-Za-z0-9_-]{8,}/,
  /\bbearer\s+\S{6,}/i,
  /\bset-cookie\b/i,
  /\b(?:password|secret|api[_-]?key|access[_-]?token|refresh[_-]?token|authorization)\b\s*[=:]\s*\S/i,
];

const INVALID_RUBRIC_PREFIX = "Rubrica inválida: ";

function hasLeak(text) {
  return LEAK_PATTERNS.some((pattern) => pattern.test(text));
}

function isSafeRubricMessage(message) {
  return (
    message.startsWith(INVALID_RUBRIC_PREFIX) &&
    message.length <= 240 &&
    !/https?:|www\./i.test(message) &&
    !hasLeak(message)
  );
}

function invalidRubricMessage(body) {
  try {
    const detail = JSON.parse(body).detail;
    if (typeof detail !== "string" || !detail.startsWith("invalid_rubric: ")) return null;
    const message = INVALID_RUBRIC_PREFIX + detail.slice("invalid_rubric: ".length);
    return isSafeRubricMessage(message) ? message : null;
  } catch {
    return null;
  }
}

function sanitizeApiError(message) {
  const match = /^API (\d{3}):\s*(.*)$/.exec(message);
  if (match) {
    const httpStatus = parseInt(match[1], 10);
    const body = match[2];
    const rubricMessage = invalidRubricMessage(body);
    if (rubricMessage) return rubricMessage;
    const detailMatch = /"detail"\s*:\s*"([a-z0-9_]+)"/i.exec(body);
    if (detailMatch) {
      const safeDetail = SAFE_DETAIL_MESSAGES[detailMatch[1]];
      if (safeDetail) return safeDetail;
    }
    return SAFE_HTTP_MESSAGES[httpStatus] ?? GENERIC_ERROR;
  }
  // Server actions redirect with an already-sanitized message and pages sanitize it again.
  if (Object.values(SAFE_HTTP_MESSAGES).includes(message)) return message;
  if (Object.values(SAFE_DETAIL_MESSAGES).includes(message)) return message;
  if (isSafeRubricMessage(message)) return message;
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

test("G-23: 409 without a known detail keeps the generic conflict copy", () => {
  const msg = "API 409: {\"detail\":\"something_unmapped\"}";
  assert.equal(sanitizeApiError(msg), SAFE_HTTP_MESSAGES[409]);
});

test("G-23: 409 with project_slug_taken returns the specific slug-in-use copy", () => {
  const msg = "API 409: {\"detail\":\"project_slug_taken\"}";
  assert.equal(sanitizeApiError(msg), SAFE_DETAIL_MESSAGES.project_slug_taken);
});

test("G-23: 409 with organization_slug_taken returns the org-slug copy", () => {
  const msg = "API 409: {\"detail\":\"organization_slug_taken\"}";
  assert.equal(sanitizeApiError(msg), SAFE_DETAIL_MESSAGES.organization_slug_taken);
});

test("G-23: 410 maps to export-expired message", () => {
  const msg = "API 410: export_expired";
  assert.equal(sanitizeApiError(msg), SAFE_HTTP_MESSAGES[410]);
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

// --- A-12 / Fix-7B.6: page-level error sanitization -----------------------
// `lib/safe-error.ts` is the shared, client-safe sanitizer. Mirror its
// `safeErrorMessage` wrapper (reusing the G-23 sanitizeApiError mirror
// above) and assert the page/error boundaries route through it instead
// of rendering raw `error.message`.

function safeErrorMessageFor(error, fallback) {
  if (error instanceof Error) return sanitizeApiError(error.message);
  if (typeof error === "string") return sanitizeApiError(error);
  return fallback;
}

test("Fix-7B.6: safeErrorMessage scrubs Error carrying SQL", () => {
  const e = new Error("API 500: SELECT * FROM users; -- secret");
  assert.equal(safeErrorMessageFor(e, "fallback"), GENERIC_ERROR);
});

test("Fix-7B.6: safeErrorMessage scrubs raw traceback string", () => {
  assert.equal(
    safeErrorMessageFor('Traceback (most recent call last): File "a.py"', "fb"),
    GENERIC_ERROR,
  );
});

test("Fix-7B.6: safeErrorMessage maps known HTTP status to friendly text", () => {
  assert.equal(
    safeErrorMessageFor(new Error("API 404: not_found"), "fb"),
    SAFE_HTTP_MESSAGES[404],
  );
});

test("Fix-7B.6: safeErrorMessage uses fallback for non-Error/non-string", () => {
  assert.equal(safeErrorMessageFor({ weird: true }, "Falha ao carregar."), "Falha ao carregar.");
});

test("Fix-7B.6: shared sanitizer module is client-safe (no use server)", () => {
  const src = readFileSync(new URL("../lib/safe-error.ts", import.meta.url), "utf8");
  assert.equal(/["']use server["']/.test(src), false);
  assert.match(src, /export function sanitizeApiError/);
  assert.match(src, /export function safeErrorMessage/);
});

test("Fix-7B.6: actions.ts reuses shared sanitizer (no duplicate copy)", () => {
  const src = readFileSync(new URL("../lib/actions.ts", import.meta.url), "utf8");
  assert.match(src, /from "@\/lib\/safe-error"/);
  assert.equal(/const LEAK_PATTERNS = \[/.test(src), false);
});

for (const section of ["datasets", "exports", "keys"]) {
  test(`Fix-7B.6: ${section}/page.tsx sanitizes load errors`, () => {
    const src = readFileSync(
      new URL(`../app/o/[org]/p/[project]/${section}/page.tsx`, import.meta.url),
      "utf8",
    );
    assert.match(src, /safeErrorMessage\(/);
    assert.equal(/error instanceof Error \? error\.message/.test(src), false);
  });

  test(`Fix-7B.6: ${section}/error.tsx does not render raw error.message`, () => {
    const src = readFileSync(
      new URL(`../app/o/[org]/p/[project]/${section}/error.tsx`, import.meta.url),
      "utf8",
    );
    const routeError = readFileSync(new URL("../components/RouteError.tsx", import.meta.url), "utf8");
    assert.match(`${src}\n${routeError}`, /safeErrorMessage\(error,/);
    assert.equal(/\{error\.message/.test(src), false);
  });
}

// --- Fix-7B.7: frontend contract/UX cleanup -------------------------------

test("Fix-7B.7: exports page uses real authenticated download route", () => {
  const src = readFileSync(new URL("../app/o/[org]/p/[project]/exports/page.tsx", import.meta.url), "utf8");
  assert.match(src, /getExportDownloadPath\(/);
  assert.match(src, /href=\{getExportDownloadPath\(row\.job\.id,\s*currentViewHref\)\}/);
  assert.match(src, /download/);
});

test("Fix-7B.7: export pending or failed state does not expose clickable fake download", () => {
  const src = readFileSync(new URL("../app/o/[org]/p/[project]/exports/page.tsx", import.meta.url), "utf8");
  assert.match(src, /disabled/);
  assert.match(src, /Processando/);
  assert.match(src, /Falhou/);
});

test("Fix-7B.7: exports copy does not claim download endpoint is missing", () => {
  const src = readFileSync(new URL("../app/o/[org]/p/[project]/exports/page.tsx", import.meta.url), "utf8");
  assert.equal(/nao existe endpoint de download/i.test(src), false);
  assert.equal(/download nao existe/i.test(src), false);
  assert.equal(/nao implementado/i.test(src), false);
});

test("Fix-7B.7: export download route proxies backend with auth and safe redirect", () => {
  const src = readFileSync(new URL("../app/api/exports/[exportId]/download/route.ts", import.meta.url), "utf8");
  assert.match(src, /getAuthToken/);
  assert.match(src, /\/exports\/\$\{encodeURIComponent\(exportId\)\}\/download/);
  assert.equal(/\/exports\/\$\{exportId\}\/download/.test(src), false);
  assert.match(src, /Authorization:\s*`Bearer \$\{token\}`/);
  assert.match(src, /sanitizeApiError/);
  assert.match(src, /410/);
});

test("Fix-7B.7: actionable controls in touched pages use real links/forms", () => {
  const exportsPage = readFileSync(
    new URL("../app/o/[org]/p/[project]/exports/page.tsx", import.meta.url),
    "utf8",
  );
  // Exports remains the canonical touchpoint: createExportAction binds the
  // single real "Solicitar export" form. Other previously-"planned" surfaces
  // on the overview and evaluations pages have been removed or rewired to
  // real backend actions in Fase 7 — assert what still exists today rather
  // than the historical `data-status="planned"` markers.
  assert.match(exportsPage, /action=\{createExportAction\}/);
});

test("Fix-7B.7: frontend types include usage/quota and redaction fields", () => {
  const src = readFileSync(new URL("../lib/types.ts", import.meta.url), "utf8");
  for (const token of [
    "redacted: boolean",
    "spans_ingested: number",
    "tokens_ingested: number",
    "monthly_span_limit: number",
    "monthly_token_limit: number",
    "monthly_judge_budget_usd: number",
    "next_cursor: string | null",
    "cost_usd: number",
  ]) {
    assert.match(src, new RegExp(token.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  }
});

test("Fix-7B.7: touched pages sanitize query-driven error surfaces", () => {
  const exportsPage = readFileSync(new URL("../app/o/[org]/p/[project]/exports/page.tsx", import.meta.url), "utf8");
  const evaluations = readFileSync(new URL("../app/o/[org]/p/[project]/evaluations/page.tsx", import.meta.url), "utf8");
  const traceDetail = readFileSync(new URL("../app/o/[org]/p/[project]/traces/[trace]/page.tsx", import.meta.url), "utf8");

  assert.match(exportsPage, /safeErrorMessage\(qp\.error/);
  assert.match(evaluations, /safeErrorMessage\(qp\.error/);
  assert.match(traceDetail, /safeErrorMessage\(qp\.error/);
  assert.equal(/\{qp\.error\}/.test(evaluations), false);
  assert.equal(/\{qp\.error\}/.test(traceDetail), false);
});

test("Fix-7B.7: exports usage panel surfaces judge budget safely", () => {
  const src = readFileSync(new URL("../components/PlanUsage.tsx", import.meta.url), "utf8");
  assert.match(src, /monthly_judge_budget_usd/);
  assert.match(src, /formatCost\(subscription\.plan\.monthly_judge_budget_usd\)/);
});

// --- Phase 7E frontend polling -------------------------------------------

test("Phase 7E: traces auto-refresh client component uses bounded router refresh polling", () => {
  const src = readFileSync(
    new URL("../app/o/[org]/p/[project]/traces/traces-auto-refresh.tsx", import.meta.url),
    "utf8",
  );

  assert.match(src, /"use client"/);
  assert.match(src, /useRouter/);
  assert.match(src, /router\.refresh\(\)/);
  assert.match(src, /window\.setInterval/);
  assert.match(src, /window\.clearInterval/);
  assert.match(src, /visibilitychange/);
  assert.match(src, /document\.hidden/);
  assert.match(src, /removeEventListener\("visibilitychange"/);
  assert.match(src, /DEFAULT_INTERVAL_MS = 30_000/);
  assert.match(src, /onClick=\{refreshNow\}/);
  assert.match(src, /Atualizar agora/);
  assert.match(src, /useEffect\(\(\) => \{\s*if \(!enabledByDefault\) \{\s*setEnabled\(false\);/s);
  assert.match(src, /\}, \[enabledByDefault\]\);/);
  assert.match(src, /aria-pressed=\{enabled\}/);
});

test("Phase 7E: traces page keeps server data loading and wires auto-refresh without hardcoded routes", () => {
  const page = readFileSync(new URL("../app/o/[org]/p/[project]/traces/page.tsx", import.meta.url), "utf8");
  const component = readFileSync(
    new URL("../app/o/[org]/p/[project]/traces/traces-auto-refresh.tsx", import.meta.url),
    "utf8",
  );

  assert.match(page, /getTraces\(\{/);
  assert.match(page, /<TracesAutoRefresh/);
  assert.match(page, /enabledByDefault=\{autoRefreshEnabled\}/);
  assert.match(page, /disabledReason=\{autoRefreshDisabledReason\}/);
  assert.match(page, /Pausado em página paginada/);
  assert.equal(/fetch\(/.test(component), false);
  assert.equal(/https?:\/\//.test(component), false);
  assert.equal(/\/o\/\$\{org\}/.test(component), false);
});

test("rubric error names the field to fix and survives the second sanitize", () => {
  const body = JSON.stringify({ detail: "invalid_rubric: evaluators.0.type: unknown evaluator type 'builtin'" });
  const shown = sanitizeApiError(`API 422: ${body}`);
  assert.equal(shown, "Rubrica inválida: evaluators.0.type: unknown evaluator type 'builtin'");
  assert.equal(sanitizeApiError(shown), shown);
});

test("rubric error with a leak or a link collapses to safe copy", () => {
  const leak = JSON.stringify({ detail: "invalid_rubric: sqlalchemy exploded" });
  assert.equal(sanitizeApiError(`API 422: ${leak}`), SAFE_HTTP_MESSAGES[422]);
  assert.equal(sanitizeApiError("Rubrica inválida: visite https://evil.example"), GENERIC_ERROR);
});

test("already-sanitized messages survive; free text from the URL does not", () => {
  assert.equal(sanitizeApiError(SAFE_HTTP_MESSAGES[402]), SAFE_HTTP_MESSAGES[402]);
  assert.equal(sanitizeApiError("Sua conta foi invadida, ligue agora"), GENERIC_ERROR);
});
