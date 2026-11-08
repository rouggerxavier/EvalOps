import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { loadTs } from "./helpers/load-ts.mjs";

function form(values = {}) {
  const data = new FormData();
  for (const [key, value] of Object.entries({ org: "org", project: "project", percentage: "20", rubric_id: "rub_1", rubric_version: "2", ...values })) {
    if (value !== null) data.set(key, value);
  }
  return data;
}
function actions(overrides = {}) {
  const saved = [], retries = [], revalidated = [];
  const api = {
    resolveProject: async () => ({ project_id: "owned-project" }),
    putSamplingConfig: async (...args) => saved.push(args),
    retrySamplingJob: async (...args) => retries.push(args),
    ...overrides,
  };
  return { ...loadTs("lib/actions.ts", {
    "next/headers": {}, "next/cache": { revalidatePath: (path) => revalidated.push(path) },
    "next/navigation": { redirect: (path) => { const error = new Error(path); error.redirect = true; throw error; } },
    "next/dist/client/components/redirect-error": { isRedirectError: (error) => error.redirect === true },
    "@/lib/flash": {}, "@/lib/api": api,
  }), saved, retries, revalidated };
}
const redirected = (error) => error.redirect === true;

test("sampling action preserves zero/100, fixed version and default disabled using owned project", async () => {
  for (const percentage of ["0", "100"]) {
    const harness = actions();
    await assert.rejects(harness.saveSamplingAction(form({ percentage, project_id: "untrusted-project" })), redirected);
    assert.deepEqual(harness.saved, [["owned-project", { enabled: false, percentage: Number(percentage), rubric_id: "rub_1", rubric_version: 2 }]]);
    assert.deepEqual(harness.revalidated, ["/o/org/p/project/settings"]);
  }
  const harness = actions();
  await assert.rejects(harness.saveSamplingAction(form({ enabled: "on" })), redirected);
  assert.equal(harness.saved[0][1].enabled, true);
});

test("sampling rejects invalid percentages and missing/fractional versions before writing", async () => {
  for (const values of [{ percentage: "" }, { percentage: "NaN" }, { percentage: "Infinity" }, { percentage: "-1" }, { percentage: "101" }, { rubric_version: "0" }, { rubric_version: "1.5" }, { rubric_version: null }, { enabled: "on", rubric_id: null, rubric_version: null }]) {
    const harness = actions();
    await assert.rejects(harness.saveSamplingAction(form(values)), redirected);
    assert.equal(harness.saved.length, 0);
  }
});

test("sampling retries never infer cost confirmation and retain authenticated project context", async () => {
  for (const confirmation of [null, "on"]) {
    const harness = actions();
    await assert.rejects(harness.retrySamplingAction(form({ trace_id: "trc_1", project_id: "untrusted", confirm_possible_charge: confirmation })), redirected);
    assert.deepEqual(harness.retries, [["owned-project", "trc_1", confirmation === "on"]]);
  }
  const invalid = actions();
  await assert.rejects(invalid.retrySamplingAction(form({ trace_id: null })), redirected);
  assert.equal(invalid.retries.length, 0);
});

test("sampling ownership failure never writes and raw database errors stay out of redirects", async () => {
  const denied = actions({ resolveProject: async () => { throw new Error("API 404: not_found"); } });
  await assert.rejects(denied.saveSamplingAction(form()), redirected);
  await assert.rejects(denied.retrySamplingAction(form({ trace_id: "trc_1" })), redirected);
  assert.equal(denied.saved.length + denied.retries.length, 0);
  const failed = actions({ putSamplingConfig: async () => { throw new Error("API 500: SELECT password FROM users; sqlite private.db"); } });
  await assert.rejects(failed.saveSamplingAction(form()), (error) => {
    assert.ok(error.redirect);
    assert.doesNotMatch(decodeURIComponent(error.message), /SELECT|password|sqlite|private\.db/);
    return true;
  });
  assert.deepEqual(failed.revalidated, []);
});

const { SamplingSettings } = loadTs("components/SamplingSettings.tsx", {
  "next/link": ({ children, ...props }) => React.createElement("a", props, children),
});
const data = {
  config: { enabled: false, percentage: 0, rubric_id: null, rubric_version: null },
  rubrics: [{ id: "rub_1", slug: "atendimento", current_version: 1 }], jobs: [],
};
const render = (value) => renderToStaticMarkup(React.createElement(SamplingSettings, { org: "org", project: "project", data: value }));

test("sampling UI is disabled by default, shows fixed rubric controls and recoverable empty/error states", () => {
  const html = render(data);
  assert.match(html, /name="enabled"/);
  assert.doesNotMatch(html, /checked=""/);
  assert.match(html, /name="percentage"[^>]*value="0"/);
  assert.match(html, /Versão fixa da rubrica/);
  assert.match(html, /todos os ambientes/);
  assert.match(html, /Nenhum trace selecionado ainda/);
  const unavailable = render(null);
  assert.match(unavailable, /Não foi possível carregar/);
  assert.doesNotMatch(unavailable, /<form/);
});

test("uncertain retry displays possible cost and an explicit unchecked required confirmation", () => {
  const job = { trace_id: "trc_1", rubric_id: "rub_1", rubric_version: 2, status: "uncertain", reason: "possible_provider_charge", run_id: null, execution_attempts: 1, retry_warning: "Repetir pode gerar nova cobrança." };
  const html = render({ ...data, jobs: [job] });
  assert.match(html, /Resultado incerto/);
  assert.match(html, /Repetir pode gerar nova cobrança/);
  assert.match(html, /name="confirm_possible_charge"[^>]*required=""/);
  assert.doesNotMatch(html, /checked=""/);
  assert.match(html, /href="\/o\/org\/p\/project\/traces\/trc_1\?tab=evaluations"/);
  assert.match(html, /atendimento/);
  assert.match(html, /v2/);
  const complete = render({ ...data, jobs: [{ ...job, status: "completed", retry_warning: null }] });
  assert.doesNotMatch(complete, /Solicitar nova tentativa/);
});

test("sampling rubric errors remain actionable without exposing raw response data", () => {
  const { sanitizeApiError } = loadTs("lib/safe-error.ts");
  assert.equal(sanitizeApiError('API 422: {"detail":"rubric_version_not_found"}'), "Esta versão da rubrica não existe. Confira o número da versão.");
  assert.equal(sanitizeApiError('API 422: {"detail":"sampling_rubric_required"}'), "Informe a rubrica e sua versão juntas.");
});

function nativeRoute({ failure, destination = "/o/org/p/project/settings?sampling_saved=1" } = {}) {
  const calls = [];
  const action = async (kind, data) => {
    calls.push([kind, data.get("confirm_possible_charge")]);
    throw failure ?? Object.assign(new Error("redirect"), { redirect: true, destination });
  };
  return { calls, ...loadTs("app/api/evaluation-sampling/route.ts", {
    "@/lib/actions": { saveSamplingAction: (data) => action("save", data), retrySamplingAction: (data) => action("retry", data) },
    "next/dist/client/components/redirect-error": { isRedirectError: (error) => error.redirect === true },
    "next/dist/client/components/redirect": { getURLFromRedirectError: (error) => error.destination },
  }) };
}
function post(intent, origin = "https://app.example", extra = {}) {
  const headers = origin ? { Origin: origin } : {};
  return new Request("https://app.example/api/evaluation-sampling", { method: "POST", headers, body: form({ intent, ...extra }) });
}

test("native sampling POST rejects missing/foreign origins and invalid actions without writing", async () => {
  const route = nativeRoute();
  for (const origin of [null, "https://foreign.example", "null"]) {
    assert.equal((await route.POST(post("save", origin))).status, 403);
  }
  assert.equal((await route.POST(post("delete"))).status, 400);
  assert.deepEqual(route.calls, []);
});

test("native sampling POST retains explicit cost confirmation and redirects with 303", async () => {
  const route = nativeRoute();
  for (const confirmation of [null, "on"]) {
    const response = await route.POST(post("retry", "https://app.example", { confirm_possible_charge: confirmation }));
    assert.equal(response.status, 303);
    assert.equal(response.headers.get("location"), "https://app.example/o/org/p/project/settings?sampling_saved=1");
  }
  assert.deepEqual(route.calls, [["retry", null], ["retry", "on"]]);
  const saved = await route.POST(post("save"));
  assert.equal(saved.status, 303);
});

test("native sampling POST contains unexpected errors and prevents external redirects", async () => {
  const failed = nativeRoute({ failure: new Error("SELECT secret FROM private") });
  const response = await failed.POST(post("save"));
  assert.equal(response.status, 500);
  assert.doesNotMatch(await response.text(), /SELECT|secret|private/);
  const external = nativeRoute({ destination: "https://foreign.example/path" });
  assert.equal((await external.POST(post("save"))).status, 500);
});


test("native POST compares Origin to browser-facing Host behind an internal Next URL", async () => {
  const route = nativeRoute();
  const request = new Request("https://localhost:3000/api/evaluation-sampling", {
    method: "POST", headers: { Host: "app.example", Origin: "https://app.example" }, body: form({ intent: "save" }),
  });
  const response = await route.POST(request);
  assert.equal(response.status, 303);
  assert.equal(response.headers.get("location"), "https://app.example/o/org/p/project/settings?sampling_saved=1");
  const foreign = new Request("https://localhost:3000/api/evaluation-sampling", {
    method: "POST", headers: { Host: "app.example", Origin: "https://foreign.example" }, body: form({ intent: "save" }),
  });
  assert.equal((await route.POST(foreign)).status, 403);
  assert.equal(route.calls.length, 1);
});


test("native POST bounds streamed forms and rejects malformed content before invoking actions", async () => {
  const route = nativeRoute();
  let cancelled = false;
  const body = new ReadableStream({
    pull(controller) { controller.enqueue(new Uint8Array(8192)); },
    cancel() { cancelled = true; },
  });
  const large = new Request("https://app.example/api/evaluation-sampling", {
    method: "POST", duplex: "half", headers: { Origin: "https://app.example", "Content-Type": "application/x-www-form-urlencoded" }, body,
  });
  assert.equal((await route.POST(large)).status, 413);
  assert.equal(cancelled, true);
  const malformed = new Request("https://app.example/api/evaluation-sampling", {
    method: "POST", headers: { Origin: "https://app.example", "Content-Type": "application/json" }, body: "{}",
  });
  assert.equal((await route.POST(malformed)).status, 400);
  assert.deepEqual(route.calls, []);
});
