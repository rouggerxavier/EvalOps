import test from "node:test";
import assert from "node:assert/strict";
import { loadTs } from "./helpers/load-ts.mjs";

function form(environment, extra = {}) {
  const data = new FormData();
  for (const [key, value] of Object.entries({ org: "org", project: "project", trace_id: "trace-1", ...extra })) data.set(key, value);
  if (environment !== undefined) data.set("environment", environment);
  return data;
}

function harness({ session = { token: "personal-session" }, api = {} } = {}) {
  const calls = [];
  const { hideTraceAction } = loadTs("lib/actions.ts", {
    "next/headers": {}, "@/lib/flash": {},
    "@/lib/auth": { getSession: async () => session },
    "next/cache": { revalidatePath: (path) => calls.push(["revalidate", path]) },
    "next/navigation": { redirect: (url) => { throw Object.assign(new Error(url), { redirect: true }); } },
    "next/dist/client/components/redirect-error": { isRedirectError: (error) => error.redirect === true },
    "@/lib/api": {
      resolveProject: async (...args) => { calls.push(["resolve", ...args]); return { project_id: "owned-project" }; },
      getTrace: async (id) => { calls.push(["get", id]); return { trace: { id, project_id: "owned-project" } }; },
      hideTrace: async (...args) => calls.push(["hide", ...args]), ...api,
    },
  });
  return { run: (data) => hideTraceAction({ error: null }, data), calls };
}

for (const environment of [undefined, "", "dev", "staging", "prod", "prod&unexpected=1"]) {
  test(`hide action validates scope and preserves only allowed environment ${JSON.stringify(environment)}`, async () => {
    const h = harness();
    await assert.rejects(h.run(form(environment, { project_id: "tampered" })), (error) => {
      assert.equal(error.redirect, true);
      const url = new URL(error.message, "http://test");
      assert.equal(url.pathname, "/o/org/p/project/traces");
      assert.equal(url.searchParams.get("environment"), environment === "prod&unexpected=1" ? null : environment ?? null);
      assert.equal(url.searchParams.has("unexpected"), false);
      return true;
    });
    assert.deepEqual(h.calls, [["resolve", "org", "project"], ["get", "trace-1"], ["hide", "trace-1", "personal-session"],
      ["revalidate", "/o/org/p/project/traces"], ["revalidate", "/o/org/p/project/traces/trace-1"]]);
  });
}

test("hide action refuses fallback-only sessions, malformed IDs and a trace from another project", async () => {
  const noSession = harness({ session: null });
  assert.match((await noSession.run(form())).error, /conta pessoal/);
  assert.deepEqual(noSession.calls, []);
  const invalid = harness();
  for (const extra of [{ trace_id: "../other" }, { org: "../foreign" }, { project: "other?x=1" }, { trace_id: "x".repeat(65) }]) {
    assert.match((await invalid.run(form(undefined, extra))).error, /inválido/);
  }
  assert.deepEqual(invalid.calls, []);
  const foreign = harness({ api: { getTrace: async () => ({ trace: { project_id: "foreign" } }) } });
  assert.match((await foreign.run(form())).error, /neste projeto/);
  assert.deepEqual(foreign.calls, [["resolve", "org", "project"]]);
});

for (const stage of ["resolveProject", "getTrace", "hideTrace"]) {
  for (const [status, expected] of [[401, /sessão expirou/], [403, /permissão/], [404, /indisponível/], [500, /Tente novamente/]]) {
    test(`hide action safely handles ${status} at ${stage}`, async () => {
      const h = harness({ api: { [stage]: async () => { throw new Error(`API ${status}: SELECT token FROM secrets; private.db`); } } });
      const result = await h.run(form("prod"));
      assert.match(result.error, expected);
      assert.doesNotMatch(result.error, /SELECT|token|secrets|private\.db/);
      assert.equal(h.calls.some(([name]) => name === "revalidate"), false);
      if (stage !== "hideTrace") assert.equal(h.calls.some(([name]) => name === "hide"), false);
    });
  }
}

test("hide API uses only the explicit personal token, accepts empty 204 and suppresses raw API errors", async () => {
  const previousFetch = globalThis.fetch;
  let status = 204;
  let request;
  globalThis.fetch = async (...args) => {
    request = args;
    return new Response(status === 204 ? null : "secret error", { status });
  };
  try {
    const { hideTrace } = loadTs("lib/api.ts", {
      react: { cache: (fn) => fn },
      "./auth": { getAuthToken: () => { throw new Error("fallback must not be used"); } },
      "./config": { getApiBaseUrl: () => "http://fake.test/v1" },
    });
    await hideTrace("trace/id", "real-session");
    assert.equal(request[0], "http://fake.test/v1/traces/trace%2Fid");
    assert.deepEqual(request[1], { method: "DELETE", headers: { Authorization: "Bearer real-session" }, cache: "no-store" });
    for (status of [200, 401, 403, 404, 500]) await assert.rejects(hideTrace("id", "real-session"), { message: `API ${status}` });
  } finally {
    globalThis.fetch = previousFetch;
  }
});
