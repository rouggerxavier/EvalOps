import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { loadTs } from "./helpers/load-ts.mjs";

const trace = (id, last_verdict) => ({
  id, last_verdict, project_id: "project", organization_id: "org", name: id,
  environment: "dev", status: "ok", started_at: "2026-11-08T10:00:00Z",
  ended_at: "2026-11-08T10:00:00Z", created_at: "2026-11-08T10:00:00Z",
  duration_ms: 10, total_cost_usd: 0, total_tokens_in: 0, total_tokens_out: 0,
  tags: {}, metadata: {}, redacted: false, last_score: 1,
});

async function render(rows, searchParams = {}, next_cursor = null) {
  let requested;
  const { default: Page } = loadTs("app/o/[org]/p/[project]/traces/page.tsx", {
    "@/lib/api": {
      hasAuthToken: async () => true,
      resolveProject: async () => ({ project_id: "project" }),
      getTraces: async (opts) => { requested = opts; return { data: rows, next_cursor }; },
      getProjectEvaluations: () => { throw new Error("Global evaluation history must not supply list verdicts"); },
    },
    "@/lib/active-env": { getActiveEnvironment: async () => "dev" },
    "@/lib/actions": { bulkFlagTracesAction: async () => {} },
    "./traces-auto-refresh": { TracesAutoRefresh: () => null },
  });
  const element = await Page({ params: Promise.resolve({ org: "org", project: "project" }), searchParams: Promise.resolve(searchParams) });
  return { html: renderToStaticMarkup(element), requested };
}

test("trace list renders API verdicts with their scores without global evaluation history", async () => {
  const { html } = await render([
    trace("old-approved", "approved"), trace("rejected", "rejected"),
    trace("partial", "partial"), trace("no-run", "unknown"),
  ]);
  assert.match(html, /old-approved/);
  assert.match(html, /Aprovado/);
  assert.match(html, /Reprovado/);
  assert.match(html, /Parcial/);
  assert.match(html, /Sem dados/);
  assert.match(html, /1\.00/);
});

test("verdict reaches the API before pagination and persists in next-page links", async () => {
  const { html, requested } = await render([trace("old-approved", "approved")], {
    verdict: "approved", cursor: "first", status: "ok", score_lt: "0.5",
  }, "second");
  assert.equal(requested.verdict, "approved");
  assert.equal(requested.cursor, "first");
  assert.equal(requested.environment, "dev");
  assert.equal(requested.status, "ok");
  assert.equal(requested.score_lt, 0.5);
  assert.match(html, /old-approved/);
  assert.match(html, /verdict=approved[^\"]*cursor=second/);
  assert.match(html, /Mostrando 1 trace/);
});

test("invalid verdicts are dropped and missing verdicts render as Sem dados", async () => {
  const { html, requested } = await render([trace("no-run")], { verdict: "invalid" });
  assert.equal(requested.verdict, undefined);
  assert.match(html, /Sem dados/);
});

test("getTraces serializes verdict alongside the existing filters", async () => {
  const previousFetch = globalThis.fetch;
  let url;
  globalThis.fetch = async (value) => { url = value; return { ok: true, json: async () => ({ data: [], next_cursor: null }) }; };
  try {
    const { getTraces } = loadTs("lib/api.ts", {
      react: { cache: (fn) => fn },
      "./auth": { getAuthToken: async () => "token" },
      "./config": { getApiBaseUrl: () => "http://api.test/v1" },
    });
    await getTraces({ projectId: "project", verdict: "unknown", cursor: "next", score_lt: 0.5, environment: "dev" });
    const params = new URL(url).searchParams;
    assert.equal(params.get("verdict"), "unknown");
    assert.equal(params.get("cursor"), "next");
    assert.equal(params.get("score_lt"), "0.5");
    assert.equal(params.get("environment"), "dev");
  } finally {
    globalThis.fetch = previousFetch;
  }
});
