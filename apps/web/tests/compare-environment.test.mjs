import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { loadTs } from "./helpers/load-ts.mjs";

const base = "/o/org/p/project/traces";
const trace = { id: "left", project_id: "project", name: "Execução", environment: "dev", status: "ok",
  created_at: "2026-11-08T10:00:00Z", duration_ms: 10, total_cost_usd: 0,
  total_tokens_in: 0, total_tokens_out: 0, metadata: {}, tags: {} };

for (const environment of [undefined, "", "prod"]) {
  test(`detail compare form/action/return preserves ${environment === undefined ? "absence" : JSON.stringify(environment)}`, async () => {
    const { default: Detail } = loadTs("app/o/[org]/p/[project]/traces/[trace]/page.tsx", {
      "@/components/ui/Modal": { Modal: ({ title, children }) => title === "Comparar com outro trace" ? children : null },
      "@/lib/actions": { compareTracesAction: "/compare" },
      "@/lib/api": { hasAuthToken: async () => true, resolveProject: async () => ({ project_id: "project", membership: { permissions: ["read"] } }), getTrace: async () => ({ trace, spans: [], feedback: [], flags: [] }),
        getRubrics: async () => ({ data: [] }), getTraces: async () => ({ data: [{ ...trace, id: "right" }], next_cursor: null }),
        getTraceEvaluations: async () => ({ data: [] }) },
    });
    const params = Promise.resolve({ org: "org", project: "project", trace: "left" });
    const html = renderToStaticMarkup(await Detail({ params, searchParams: Promise.resolve({ environment }) }));
    const form = html.match(/<form action="\/compare">([\s\S]*?)<\/form>/)[1];
    const data = new FormData();
    for (const [, name, value] of form.matchAll(/<input[^>]*name="([^"]+)"[^>]*value="([^"]*)"/g)) data.set(name, value);
    data.set("right_trace_id", form.match(/<select[^>]*name="right_trace_id"[\s\S]*?<option value="([^"]+)"/)[1]);
    assert.equal(data.get("environment"), environment ?? null);
    for (const failure of [false, true]) {
      let requested;
      const { compareTracesAction } = loadTs("lib/actions.ts", {
        "next/headers": {}, "next/cache": {}, "@/lib/flash": {},
        "next/navigation": { redirect: (url) => { throw Object.assign(new Error(url), { redirect: true }); } },
        "next/dist/client/components/redirect-error": { isRedirectError: (error) => error.redirect === true },
        "@/lib/api": { compareTraces: async (body) => { requested = body; if (failure) throw new Error("Comparison failed"); } },
      });
      await assert.rejects(compareTracesAction(data), (error) => {
        assert.equal(error.redirect, true);
        const url = new URL(error.message, "http://web.test");
        assert.equal(url.pathname, `${base}/${failure ? "left" : "compare"}`);
        assert.equal(url.searchParams.get("environment"), environment ?? null);
        return true;
      });
      assert.deepEqual(requested, { left_trace_id: "left", right_trace_id: "right" });
    }
    const { default: Compare } = loadTs("app/o/[org]/p/[project]/traces/compare/page.tsx", {
      "@/lib/api": { hasAuthToken: async () => true },
    });
    const compare = renderToStaticMarkup(await Compare({ params, searchParams: Promise.resolve({ environment }) }));
    assert.ok(compare.includes(`href="${base}${environment === undefined ? "" : `?environment=${environment}`}"`));
  });
}

test("compare action drops untrusted environments and encodes trace IDs in its redirect", async () => {
  const { compareTracesAction } = loadTs("lib/actions.ts", {
    "next/headers": {}, "next/cache": {}, "@/lib/flash": {},
    "next/navigation": { redirect: (url) => { throw Object.assign(new Error(url), { redirect: true }); } },
    "next/dist/client/components/redirect-error": { isRedirectError: (error) => error.redirect === true },
    "@/lib/api": { compareTraces: async () => {} },
  });
  const data = new FormData();
  for (const [key, value] of Object.entries({ org: "org", project: "project", left_trace_id: "left&environment=dev", right_trace_id: "right", environment: "prod&unexpected=1" })) data.set(key, value);
  await assert.rejects(compareTracesAction(data), (error) => {
    const url = new URL(error.message, "http://web.test");
    assert.equal(url.searchParams.has("environment"), false);
    assert.equal(url.searchParams.get("left"), "left&environment=dev");
    assert.equal(url.searchParams.has("unexpected"), false);
    return error.redirect;
  });
});
