import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { loadTs } from "./helpers/load-ts.mjs";

const params = Promise.resolve({ org: "org", project: "project" });
const resolved = (permissions) => ({ org_id: "org", project_id: "project", membership: { role: "role-is-not-policy", permissions } });
const render = (node) => renderToStaticMarkup(node);

test("shell gets read data for everyone but plan/usage only with server admin permission", async () => {
  for (const permissions of [["read"], ["read", "write"], ["admin", "read", "write", "destructive"], []]) {
    const calls = [];
    let props;
    const { AppShell } = loadTs("components/AppShell.tsx", {
      "@/lib/active-env": { getActiveEnvironment: async () => "prod" },
      "@/components/OpsShellFrame": { OpsShellFrame: (p) => { props = p; return null; } },
      "@/lib/api": {
        resolveProject: async () => resolved(permissions), getNotifications: async () => ({ data: [] }), getProjects: async () => ({ data: [] }), getAttention: async () => ({ count: 0 }),
        getOrganizationUsage: async () => { calls.push("usage"); return { traces_ingested: 1 }; },
        getOrganizationSubscription: async () => { calls.push("plan"); return { plan: { monthly_trace_limit: 100 } }; },
      },
    });
    render(await AppShell({ org: "org", project: "project", initials: "QA", children: null }));
    assert.deepEqual(calls, permissions.includes("admin") ? ["usage", "plan"] : []);
    assert.deepEqual(props.permissions, permissions);
  }
});

test("direct keys route denies before keys and flash secrets are fetched", async () => {
  const { default: Page } = loadTs("app/o/[org]/p/[project]/keys/page.tsx", {
    "@/lib/api": { hasAuthToken: async () => true, resolveProject: async () => resolved(["read", "write"]), getApiKeys: () => assert.fail("keys fetched") },
    "@/lib/flash": { consumeApiKeyFlash: () => assert.fail("secret read") },
  });
  const html = render(await Page({ params, searchParams: Promise.resolve({ created: "1" }) }));
  assert.match(html, /Acesso restrito/); assert.doesNotMatch(html, /<form|Criar chave/);
});

test("settings non-admin reads members without fetching administrative configuration", async () => {
  for (const permissions of [["read"], ["read", "write"]]) {
    let management;
    const { default: Page } = loadTs("app/o/[org]/p/[project]/settings/page.tsx", {
      "@/lib/api": new Proxy({ hasAuthToken: async () => true, resolveProject: async () => resolved(permissions), getMembers: async () => ({ data: [], next_cursor: "next" }) }, {
        get: (target, key) => target[key] ?? (() => assert.fail(`administrative fetch: ${String(key)}`)),
      }),
      "@/lib/auth": { getSession: async () => ({ user: { id: "self" } }) },
      "./membership-management": { MembershipManagement: (props) => { management = props; return React.createElement("p", null, "Membros"); } },
    });
    const html = render(await Page({ params, searchParams: Promise.resolve({}) }));
    assert.equal(management.canAdmin, false); assert.equal(management.memberCursor, "next");
    assert.match(html, /Membros/); assert.doesNotMatch(html, /<form|Plano e uso|Quality Gate/);
  }
});

test("member can write trace actions, viewer keeps compare, only destructive can hide", () => {
  for (const [canWrite, canDestructive] of [[false, false], [true, false], [true, true]]) {
    const { TraceHeaderActions } = loadTs("app/o/[org]/p/[project]/traces/[trace]/trace-actions.tsx", {
      "@/components/ui/Modal": { Modal: () => null }, "@/lib/actions": {},
    });
    const html = render(React.createElement(TraceHeaderActions, { org: "org", project: "project", traceId: "trace", rubrics: [], compareCandidates: [], canWrite, canDestructive }));
    assert.match(html, /Comparar/); assert.equal(html.includes("Ocultar trace"), canDestructive);
    for (const name of ["Marcar para revisão", "Repetir chamada LLM", "Avaliar"]) assert.equal(html.includes(name), canWrite, name);
  }
});

test("viewer cannot mark notifications read while retaining notification content", () => {
  const { NotificationsBell } = loadTs("components/ui/NotificationsBell.tsx", { react: { useState: () => [true, () => {}] }, "@/lib/actions": { markNotificationsReadAction: "/mark" } });
  for (const canWrite of [false, true]) {
    const html = render(React.createElement(NotificationsBell, { canWrite, notifications: [{ id: "notice", kind: "info", title: "Nova avaliação", read_at: null }], org: "org", project: "project", projectId: "project", currentPath: "/" }));
    assert.match(html, /Nova avaliação/); assert.equal(html.includes("Marcar lidas"), canWrite);
  }
});

test("viewer sees prompt content without creation affordances", async () => {
  for (const permissions of [["read"], ["read", "write"]]) {
    const { default: Page } = loadTs("app/o/[org]/p/[project]/prompts/page.tsx", {
      "@/lib/api": { hasAuthToken: async () => true, resolveProject: async () => resolved(permissions), getPrompts: async () => ({ data: [] }) },
      "@/lib/actions": { createPromptAction: "/create" },
    });
    const html = render(await Page({ params, searchParams: Promise.resolve({}) }));
    assert.match(html, /Prompts/); assert.equal(html.includes("Novo prompt"), permissions.includes("write")); assert.equal(html.includes('action="/create"'), permissions.includes("write"));
  }
});

test("project switcher exposes creation only with admin", () => {
  const { WorkspaceSwitcher } = loadTs("components/ui/WorkspaceSwitcher.tsx", { "next/navigation": { useRouter: () => ({ push() {} }) } });
  for (const canAdmin of [false, true]) {
    const html = render(React.createElement(WorkspaceSwitcher, { canAdmin, current: "org/project", projects: [{ org: "org", project: "project", label: "Projeto" }] }));
    assert.equal(html.includes("Novo projeto"), canAdmin); assert.match(html, /Projeto/);
  }
});

test("trace detail cannot derive affordances from another project in the URL", async () => {
  const { default: Page } = loadTs("app/o/[org]/p/[project]/traces/[trace]/page.tsx", {
    "next/navigation": { notFound: () => { throw new Error("NOT_FOUND"); } },
    "@/lib/api": { hasAuthToken: async () => true, resolveProject: async () => resolved(["admin", "destructive", "read", "write"]), getTrace: async () => ({ trace: { project_id: "other-project" } }), getRubrics: () => assert.fail("foreign trace loaded") },
  });
  await assert.rejects(Page({ params: Promise.resolve({ org: "org", project: "project", trace: "foreign" }), searchParams: Promise.resolve({}) }), /NOT_FOUND/);
});
