import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { loadTs } from "./helpers/load-ts.mjs";

async function render(query = {}, { cookie = "prod", attentionError = false, empty = false } = {}) {
  const calls = {};
  const record = (name, result) => async (...args) => { calls[name] = args; return result; };
  const { default: Page } = loadTs("app/o/[org]/p/[project]/page.tsx", {
    "next/headers": { cookies: async () => ({ get: () => ({ value: cookie }) }) },
    "next/link": ({ children, ...props }) => React.createElement("a", props, children),
    "@/components/QualityGateCard": { QualityGateCard: () => null },
    "@/lib/actions": {},
    "@/lib/api": {
      hasAuthToken: async () => true,
      resolveProject: async () => ({ project_id: "owned-project", project_name: "Project" }),
      getOverview: record("overview", { kpis: { traces: 0, latency_p95_ms: 0, cost_usd: 0, error_rate: 0 }, cost_by_day: [], model_breakdown: [] }),
      getAttention: async (...args) => {
        calls.attention = args;
        if (attentionError) throw new Error("unavailable");
        return { count: empty ? 0 : 1, items: empty ? [] : [{ trace_id: "dev_partial", cause: "partial_trace", service: "app", at: "2026-11-08T12:00:00Z" }] };
      },
      getSdkStatus: async () => null,
      getRubrics: async () => ({ data: [] }),
      getTraces: record("traces", { data: [], next_cursor: null }),
      getQualityGateStatus: record("gate", null),
    },
  });
  const page = await Page({ params: Promise.resolve({ org: "org", project: "project" }), searchParams: Promise.resolve(query) });
  return { html: renderToStaticMarkup(page), calls };
}

test("overview sends the cookie environment to attention and the other environment-scoped requests", async () => {
  const { html, calls } = await render({}, { cookie: "dev" });
  assert.deepEqual(calls.attention, ["owned-project", "dev"]);
  assert.equal(calls.overview[1], "dev");
  assert.equal(calls.traces[0].environment, "dev");
  assert.equal(calls.gate[1], "dev");
  assert.match(html, /últimas 24 horas · Dev/);
  assert.match(html, /href="\/o\/org\/p\/project\/traces\/dev_partial\?environment=dev"/);
  assert.match(html, /href="\/o\/org\/p\/project\/evaluations\?environment=dev"/);
});

test("query environment overrides the cookie and clearing it stays explicit in navigation", async () => {
  const selected = await render({ environment: "staging", window: "30d" });
  assert.deepEqual(selected.calls.attention, ["owned-project", "staging"]);
  assert.deepEqual(selected.calls.overview, ["owned-project", "staging", "30d"]);
  const all = await render({ environment: "", window: "7d" });
  assert.deepEqual(all.calls.attention, ["owned-project", undefined]);
  assert.equal(all.calls.traces[0].environment, undefined);
  assert.match(all.html, /últimas 24 horas · Todos os ambientes/);
  for (const path of ["traces", "traces/dev_partial", "evaluations"]) {
    assert.ok(all.html.includes(`href="/o/org/p/project/${path}?environment="`), path);
  }
  assert.match(all.html, /href="\/o\/org\/p\/project\?window=7d&amp;environment="/);
  assert.match(all.html, /name="environment" value=""/);
});

test("attention keeps distinct empty and unavailable states with an environment-scoped recovery link", async () => {
  const empty = await render({ environment: "staging" }, { empty: true });
  assert.match(empty.html, /Nenhum trace com erro ou parcial nas últimas 24 horas/);
  const failed = await render({ environment: "dev" }, { attentionError: true });
  assert.match(failed.html, /Não foi possível carregar os traces que precisam de atenção/);
  assert.match(failed.html, /href="\/o\/org\/p\/project\/traces\?environment=dev"/);
});

test("attention and coverage clients serialize only a selected environment and keep the coverage window", async () => {
  const previousFetch = globalThis.fetch;
  const urls = [];
  globalThis.fetch = async (value) => { urls.push(new URL(value)); return { ok: true, json: async () => ({}) }; };
  try {
    const api = loadTs("lib/api.ts", {
      react: { cache: (fn) => fn },
      "./auth": { getAuthToken: async () => "token" },
      "./config": { getApiBaseUrl: () => "http://api.test/v1" },
    });
    await api.getAttention("project", "dev");
    await api.getCoverage("project", "30d", "staging");
    await api.getAttention("project");
    await api.getCoverage("project", "7d");
    assert.equal(urls[0].searchParams.get("environment"), "dev");
    assert.equal(urls[1].searchParams.get("environment"), "staging");
    assert.equal(urls[1].searchParams.get("window"), "30d");
    assert.equal(urls[2].searchParams.has("environment"), false);
    assert.equal(urls[3].searchParams.has("environment"), false);
    assert.equal(urls[3].searchParams.get("window"), "7d");
  } finally {
    globalThis.fetch = previousFetch;
  }
});
