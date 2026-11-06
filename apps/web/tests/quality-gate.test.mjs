import { test } from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { loadTs } from "./helpers/load-ts.mjs";

const { parseQualityGateForm } = loadTs("lib/quality-gate.ts");
function form(values = {}) {
  const data = new FormData();
  for (const [key, value] of Object.entries({ org: "org", project: "project", min_score_percent: "80", max_ungrounded_percent: "5", max_avg_cost_usd: "0.05", max_p95_ms: "2000", require_zero_critical: "on", ...values })) {
    if (value !== null) data.set(key, value);
  }
  return data;
}

test("gate form: converts percentages and persists all thresholds, including zero", () => {
  assert.deepEqual(parseQualityGateForm(form()), { min_score: 0.8, max_ungrounded_rate: 0.05, max_avg_cost_usd: 0.05, max_p95_ms: 2000, require_zero_critical: true });
  assert.equal(parseQualityGateForm(form({ max_p95_ms: "0", require_zero_critical: null })).max_p95_ms, 0);
  assert.equal(parseQualityGateForm(form({ require_zero_critical: null })).require_zero_critical, false);
});

test("gate form: blank, missing, non-finite, out of range and fractional p95 are rejected", () => {
  for (const values of [{ min_score_percent: "" }, { min_score_percent: null }, { min_score_percent: "101" }, { max_ungrounded_percent: "-1" }, { max_avg_cost_usd: "Infinity" }, { max_avg_cost_usd: "NaN" }, { max_avg_cost_usd: "-1" }, { max_p95_ms: "2.5" }, { max_p95_ms: "86400001" }]) {
    assert.equal(parseQualityGateForm(form(values)), null);
  }
});

function actions(api = {}) {
  const revalidated = [];
  let saved;
  const { saveQualityGateAction } = loadTs("lib/actions.ts", {
    "next/headers": {},
    "next/cache": { revalidatePath: (path) => revalidated.push(path) },
    "next/navigation": { redirect: (url) => { const error = new Error(url); error.redirect = true; throw error; } },
    "next/dist/client/components/redirect-error": { isRedirectError: (error) => error.redirect === true },
    "@/lib/flash": {},
    "@/lib/api": {
      resolveProject: async () => ({ project_id: "resolved-owned-project" }),
      putQualityGateConfig: async (...args) => { saved = args; },
      ...api,
    },
  });
  return { saveQualityGateAction, revalidated, getSaved: () => saved };
}

test("gate action: uses authenticated project resolution, saves and refreshes settings/overview", async () => {
  const harness = actions();
  await assert.rejects(harness.saveQualityGateAction(form({ project_id: "tampered-private-project" })), (error) => error.redirect && error.message.endsWith("/settings?gate_saved=1"));
  assert.equal(harness.getSaved()[0], "resolved-owned-project");
  assert.equal(harness.getSaved()[1].min_score, 0.8);
  assert.deepEqual(harness.revalidated, ["/o/org/p/project/settings", "/o/org/p/project"]);
});

test("gate action: invalid input never writes, ownership failures and SQL errors stay safe", async () => {
  const harness = actions();
  await assert.rejects(harness.saveQualityGateAction(form({ min_score_percent: "" })), (error) => error.redirect);
  assert.equal(harness.getSaved(), undefined);
  for (const message of ['API 404: {"detail":"not_found"}', 'API 500: SELECT password FROM users; sqlite private.db']) {
    const denied = actions({ resolveProject: async () => { throw new Error(message); } });
    await assert.rejects(denied.saveQualityGateAction(form()), (error) => {
      assert.ok(error.redirect);
      assert.doesNotMatch(decodeURIComponent(error.message), /SELECT|password|sqlite|private\.db/);
      return true;
    });
    assert.equal(denied.getSaved(), undefined);
    assert.deepEqual(denied.revalidated, []);
  }
});

const { QualityGateCard } = loadTs("components/QualityGateCard.tsx", {
  "next/link": ({ children, ...props }) => React.createElement("a", props, children),
});
function gate(state = "pass") {
  return {
    status: state, window: "7d", environment: "prod", config: { configured: true },
    metrics: { trace_count: 10 },
    reasons: [
      { metric: "quality", status: state, observed: 0.9, threshold: 0.8, sample_count: 10, code: "within_threshold" },
      { metric: "ungrounded", status: state, observed: 0.02, threshold: 0.05, sample_count: 10, code: "within_threshold" },
      { metric: "avg_cost", status: state, observed: 0.01, threshold: 0.05, sample_count: 10, code: "within_threshold" },
      { metric: "p95", status: state, observed: 1000, threshold: 2000, sample_count: 10, code: "within_threshold" },
      { metric: "critical", status: state, observed: 0, threshold: 0, sample_count: 10, code: "within_threshold" },
    ],
  };
}
const render = (data) => renderToStaticMarkup(React.createElement(QualityGateCard, { gate: data, settingsHref: "/settings#quality-gate" }));
for (const [state, label] of [["pass", "Aprovado"], ["review", "Revisão necessária"], ["fail", "Reprovado"]]) {
  test(`gate card: renders backend ${state} with PT-BR result and five metrics`, () => {
    const html = render(gate(state));
    assert.match(html, new RegExp(label));
    for (const metric of ["Qualidade", "Alucinação", "Custo médio", "p95", "Regras críticas"]) assert.ok(html.includes(metric));
    assert.match(html, /90%/);
    assert.match(html, /2%/);
    assert.match(html, /href="\/settings#quality-gate"/);
  });
}

test("gate card: missing evidence, unconfigured and API failure never show approval", () => {
  const data = gate("review");
  data.config.configured = false;
  data.reasons[0] = { ...data.reasons[0], observed: null, status: "review", code: "missing_evidence" };
  const html = render(data);
  assert.match(html, /Sem evidência/);
  assert.match(html, /Salve os limites/);
  const unavailable = render(null);
  assert.match(unavailable, /Não foi possível carregar/);
  assert.doesNotMatch(unavailable, /Aprovado/);
});

test("gate form: rendered inputs reflect persisted values and checkbox state", () => {
  const { QualityGateForm } = loadTs("components/QualityGateForm.tsx", { "@/lib/actions": { saveQualityGateAction: "/save" } });
  const config = { min_score: 0.85, max_ungrounded_rate: 0.12, max_avg_cost_usd: 0.004, max_p95_ms: 750, require_zero_critical: false, configured: true };
  const html = renderToStaticMarkup(React.createElement(QualityGateForm, { config, org: "org", project: "project" }));
  assert.match(html, /name="min_score_percent"[^>]*value="85"/);
  assert.match(html, /name="max_ungrounded_percent"[^>]*value="12"/);
  assert.match(html, /name="max_avg_cost_usd"[^>]*value="0.004"/);
  assert.match(html, /name="max_p95_ms"[^>]*value="750"/);
  assert.doesNotMatch(html, /checked=""/);
  assert.match(html, /Limites salvos/);
});
