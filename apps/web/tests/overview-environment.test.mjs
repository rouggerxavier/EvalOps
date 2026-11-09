import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { loadTs } from "./helpers/load-ts.mjs";

const emptyFeedback = { feedback_count: 0, trace_count: 0, thumbs_up: 0, thumbs_down: 0, rating_count: 0, avg_rating: null };

async function render(query = {}, { cookie = "prod", attentionError = false, empty = false, feedback = emptyFeedback, traces = 0 } = {}) {
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
      getOverview: record("overview", { kpis: { traces, latency_p95_ms: 0, cost_usd: 0, error_rate: 0 }, human_feedback: feedback, cost_by_day: [], model_breakdown: [] }),
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

function feedbackCard(html) {
  return html.slice(html.lastIndexOf("<section", html.indexOf("Feedback humano")), html.indexOf("</section>", html.indexOf("Feedback humano")));
}

test("human feedback shows submissions, trace coverage and independent signal denominators in the selected cohort", async () => {
  const { html } = await render({ environment: "dev", window: "7d" }, { traces: 10, feedback: { feedback_count: 8, trace_count: 3, thumbs_up: 2, thumbs_down: 1, rating_count: 4, avg_rating: 4.25 } });
  const card = feedbackCard(html);
  assert.match(card, /Feedback dos traces na janela · últimos 7 dias · Dev/);
  assert.match(card, /Envios<\/span><strong>8<\/strong>/);
  assert.match(card, /Traces com feedback<\/span><strong>3 de 10<\/strong>/);
  assert.match(card, /Positivos<\/span><strong>66,7% · n=3<\/strong>/);
  assert.match(card, /Negativos<\/span><strong>1<\/strong>/);
  assert.match(card, /Nota média<\/span><strong>4,25 \/ 5 · n=4<\/strong>/);
  assert.match(card, /Cada envio conta. Feedback posterior atualiza os resultados./);
  assert.doesNotMatch(card, /pessoas|juiz|amostragem|aprovação/i);
  assert.ok(html.indexOf('aria-label="Indicadores do período"') < html.indexOf("Feedback humano"));
  assert.ok(html.indexOf("Feedback humano") < html.indexOf("Precisa de atenção"));
});

test("human feedback distinguishes no signals, zero approval, thumb-only and rating-only", async () => {
  const empty = feedbackCard((await render({ environment: "", window: "30d" })).html);
  assert.match(empty, /Feedback dos traces na janela · últimos 30 dias · Todos os ambientes/);
  assert.match(empty, /Positivos<\/span><strong>Sem dados · n=0<\/strong>/);
  assert.match(empty, /Nota média<\/span><strong>Sem dados · n=0<\/strong>/);
  const thumbs = feedbackCard((await render({}, { feedback: { ...emptyFeedback, feedback_count: 1, trace_count: 1, thumbs_down: 1 } })).html);
  assert.match(thumbs, /Positivos<\/span><strong>0% · n=1<\/strong>/);
  assert.match(thumbs, /Nota média<\/span><strong>Sem dados · n=0<\/strong>/);
  const rating = feedbackCard((await render({}, { feedback: { ...emptyFeedback, feedback_count: 1, trace_count: 1, rating_count: 1, avg_rating: 5 } })).html);
  assert.match(rating, /Positivos<\/span><strong>Sem dados · n=0<\/strong>/);
  assert.match(rating, /Nota média<\/span><strong>5 \/ 5 · n=1<\/strong>/);
});

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
