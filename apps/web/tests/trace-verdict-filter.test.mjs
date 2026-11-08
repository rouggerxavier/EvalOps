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

test("invalid tag stays editable with an explicit warning and is not applied", async () => {
  const { html, requested } = await render([trace("one", "unknown")], { tag: "whatsapp" }, "next");
  assert.equal(requested.tag, undefined);
  assert.match(html, /<details[^>]*open=""/);
  assert.match(html, /name="tag"[^>]*aria-invalid="true"[^>]*value="whatsapp"/);
  assert.match(html, /name="tag"[^>]*aria-describedby="tag-error"/);
  assert.doesNotMatch(html.match(/<input[^>]*name="tag"[^>]*>/)[0], /pattern=/);
  assert.match(html, /role="alert"[^>]*>Tag não aplicada\. Use o formato chave:valor, como canal:whatsapp\./);
  assert.doesNotMatch(html, /tag=whatsapp/);
  assert.doesNotMatch(html, /Mais filtros<span class="tab__count">1/);
});

test("invalid tag from the URL is escaped in the editable field", async () => {
  const tag = '\"><script>alert("tag")</script>';
  const { html, requested } = await render([], { tag });
  assert.equal(requested.tag, undefined);
  assert.match(html, /value="&quot;&gt;&lt;script&gt;alert\(&quot;tag&quot;\)&lt;\/script&gt;"/);
  assert.doesNotMatch(html, /<script>/);
});

test("empty and whitespace-only tags stay optional and do not apply a filter", async () => {
  for (const tag of ["", "   "]) {
    const { html, requested } = await render([], { tag });
    assert.equal(requested.tag, undefined);
    assert.match(html, /name="tag"[^>]*value=""/);
    assert.doesNotMatch(html, /Tag não aplicada|aria-invalid="true"/);
  }
});

test("valid tag keeps the format hint and existing filters through pagination", async () => {
  const { html, requested } = await render([trace("one", "approved")], {
    tag: "canal:whatsapp", verdict: "approved", cursor: "first", tab: "slow", slow_kind: "llm",
    environment: "dev", name: "support", q: "answer", conversation_id: "conversation",
    since: "2026-11-01", until: "2026-11-08", user_ref: "user", model: "model", failed: "true", score_lt: "0.5",
  }, "second");
  assert.equal(requested.tag, "canal:whatsapp");
  assert.equal(requested.since, "2026-11-01T00:00:00");
  assert.equal(requested.until, "2026-11-08T23:59:59.999");
  assert.match(html, /name="tag"[^>]*title="Use o formato chave:valor, como canal:whatsapp"/);
  assert.doesNotMatch(html, /Tag não aplicada/);
  const href = [...html.matchAll(/href="([^"]+)"/g)].map((match) => match[1].replaceAll("&amp;", "&"))
    .find((value) => value.includes("cursor=second"));
  const params = new URL(href, "http://web.test").searchParams;
  for (const [key, value] of Object.entries({ tag: "canal:whatsapp", verdict: "approved", cursor: "second", tab: "slow", slow_kind: "llm", environment: "dev", name: "support", q: "answer", conversation_id: "conversation", since: "2026-11-01", until: "2026-11-08", user_ref: "user", model: "model", failed: "true", score_lt: "0.5" })) {
    assert.equal(params.get(key), value, key);
  }
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
