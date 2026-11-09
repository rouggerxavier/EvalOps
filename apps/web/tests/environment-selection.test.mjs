import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { loadTs } from "./helpers/load-ts.mjs";

const base = "/o/org/p/project";
const link = ({ children, ...props }) => React.createElement("a", props, children);
const headers = { cookies: async () => ({ get: () => ({ value: "dev" }) }) };

for (const [query, expected] of [["environment=", "all"], ["environment=prod", "prod"], ["", "dev"]]) {
  test(`cookie dev + ${query || "absent query"}: data, chip and shell navigation agree`, async () => {
    const searchParams = new URLSearchParams(query);
    const overrides = {
      "next/headers": headers,
      "next/link": link,
      "next/navigation": { usePathname: () => `${base}/traces/trace`, useSearchParams: () => searchParams },
      "@/lib/actions": {}, "@/lib/auth-actions": {},
      "@/components/ui/NotificationsBell": { NotificationsBell: () => null },
      "@/components/ui/WorkspaceSwitcher": { WorkspaceSwitcher: () => null },
    };
    const { EvoTopbar } = loadTs("components/EvoTopbar.tsx", overrides);
    const { Sidebar } = loadTs("components/Sidebar.tsx", overrides);
    const { AppShell } = loadTs("components/AppShell.tsx", {
      ...overrides,
      "@/lib/api": { resolveProject: async () => null },
      "@/components/OpsShellFrame": { OpsShellFrame: (props) => React.createElement(React.Fragment, null,
        React.createElement(EvoTopbar, { ...props, mobileMenuOpen: false, onMenuToggle() {} }),
        React.createElement(Sidebar, { ...props, mobileMenuOpen: false, onNavigate() {}, onClose() {} })),
      },
    });
    const { getActiveEnvironment } = loadTs("lib/active-env.ts", { "next/headers": headers });
    assert.equal(await getActiveEnvironment(searchParams.get("environment") ?? undefined), expected === "all" ? undefined : expected);
    const html = renderToStaticMarkup(await AppShell({ org: "org", project: "project", initials: "OR" }));
    const select = html.match(/<select[^>]*name="environment"[\s\S]*?<\/select>/)[0];
    assert.match(select, new RegExp(`<option value="${expected}" selected=""`));
    const suffix = query ? `?${query}` : "";
    assert.ok(html.includes(`href="${base}/traces${suffix}"`));
    assert.ok(html.includes(`href="${base}${suffix}"`));
    if (query) assert.ok(html.includes(`<input type="hidden" name="environment" value="${searchParams.get("environment")}"`));
  });

  test(`traces keep ${query || "cookie fallback"} through pagination, tabs and clearing filters`, async () => {
    let requested;
    const { default: Page } = loadTs("app/o/[org]/p/[project]/traces/page.tsx", {
      "next/headers": headers, "next/link": link,
      "@/lib/api": { hasAuthToken: async () => true, resolveProject: async () => ({ project_id: "project" }),
        getTraces: async (opts) => { requested = opts; return { data: [], next_cursor: "next" }; } },
      "./traces-auto-refresh": { TracesAutoRefresh: () => null },
      "./traces-table": { TracesEmpty: () => null, TracesTable: () => null },
    });
    const html = renderToStaticMarkup(await Page({ params: Promise.resolve({ org: "org", project: "project" }),
      searchParams: Promise.resolve({ ...Object.fromEntries(new URLSearchParams(query)), q: "missing", cursor: "first" }) }));
    assert.equal(requested.environment, expected === "all" ? undefined : expected);
    const hrefs = [...html.matchAll(/href="([^"]+)"/g)].map((m) => m[1].replaceAll("&amp;", "&"));
    for (const href of [hrefs.find((href) => href.includes("cursor=next")), hrefs.find((href) => href.includes("tab=errors")), hrefs.find((href) => href.includes("q=missing") && !href.includes("cursor=") && !href.includes("tab="))]) {
      assert.equal(new URL(href, "http://web.test").searchParams.get("environment"), expected === "all" ? "" : expected, href);
    }
    const clear = html.match(/href="([^"]+)"[^>]*>Limpar filtros/)[1].replaceAll("&amp;", "&");
    assert.equal(new URL(clear, "http://web.test").searchParams.get("environment"), expected === "all" ? "" : expected);
  });
}

test("all environments survives opening a trace, its tabs, returning and opening compare/export", async () => {
  const trace = { id: "trace", name: "Execução", project_id: "project", environment: "dev", status: "ok",
    created_at: "2026-11-08T10:00:00Z", duration_ms: 10, total_cost_usd: 0,
    total_tokens_in: 0, total_tokens_out: 0, tags: {}, metadata: {} };
  const overrides = {
    "next/headers": headers, "next/link": link,
    "@/lib/actions": {},
    "@/lib/api": { hasAuthToken: async () => true, resolveProject: async () => ({ project_id: "project" }),
      getTraces: async () => ({ data: [trace], next_cursor: null }), getTrace: async () => ({ trace, spans: [], feedback: [], flags: [] }),
      getRubrics: async () => ({ data: [] }), getTraceEvaluations: async () => ({ data: [] }) },
    "./traces-auto-refresh": { TracesAutoRefresh: () => null },
    "./trace-actions": { TraceHeaderActions: () => null },
  };
  const params = Promise.resolve({ org: "org", project: "project", trace: "trace" });
  const searchParams = Promise.resolve({ environment: "" });
  const { default: List } = loadTs("app/o/[org]/p/[project]/traces/page.tsx", overrides);
  const list = renderToStaticMarkup(await List({ params, searchParams }));
  for (const path of ["traces/trace", "traces/compare", "exports"]) assert.ok(list.includes(`href="${base}/${path}?environment="`), path);
  const { default: Detail } = loadTs("app/o/[org]/p/[project]/traces/[trace]/page.tsx", overrides);
  const detail = renderToStaticMarkup(await Detail({ params, searchParams }));
  assert.ok(detail.includes(`href="${base}/traces?environment="`));
  assert.ok(detail.includes(`href="${base}/traces/trace?tab=steps&amp;environment="`));
  const { default: Compare } = loadTs("app/o/[org]/p/[project]/traces/compare/page.tsx", overrides);
  const compare = renderToStaticMarkup(await Compare({ params, searchParams }));
  assert.ok(compare.includes(`href="${base}/traces?environment="`));
});

test("keyboard G T preserves an explicit all-environments query", () => {
  const previousWindow = globalThis.window;
  const previousElement = globalThis.HTMLElement;
  let listener, destination, cleanup;
  globalThis.HTMLElement = class {};
  globalThis.window = { addEventListener: (_, handler) => { listener = handler; }, removeEventListener() {}, setTimeout: () => 1, clearTimeout() {} };
  try {
    const { EvoShortcuts } = loadTs("components/EvoShortcuts.tsx", {
      react: { useEffect: (effect) => { cleanup = effect(); } },
      "next/navigation": { useParams: () => ({ org: "org", project: "project" }),
        useSearchParams: () => new URLSearchParams("environment="), useRouter: () => ({ push: (href) => { destination = href; } }) },
    });
    EvoShortcuts();
    listener({ key: "g", target: null });
    listener({ key: "t", target: null, preventDefault() {} });
    assert.equal(destination, `${base}/traces?environment=`);
  } finally {
    cleanup?.(); globalThis.window = previousWindow; globalThis.HTMLElement = previousElement;
  }
});
