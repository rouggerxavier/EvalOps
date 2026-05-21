import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const nav = readFileSync(new URL("../components/app-shell-nav.ts", import.meta.url), "utf8");
const sidebar = readFileSync(new URL("../components/Sidebar.tsx", import.meta.url), "utf8");
const topbar = readFileSync(new URL("../components/EvoTopbar.tsx", import.meta.url), "utf8");
const layout = readFileSync(new URL("../app/o/[org]/p/[project]/layout.tsx", import.meta.url), "utf8");

test("P1 AppShell: authenticated layout uses scoped internal shell", () => {
  assert.match(layout, /import \{ AppShell \}/);
  assert.match(layout, /<AppShell org=\{org\} project=\{project\} initials=\{initials\}>/);
  assert.doesNotMatch(layout, /EvoTopbar/);
  assert.doesNotMatch(layout, /<Sidebar/);
});

test("P1 AppShell: sidebar preserves real project modules and routes", () => {
  for (const label of [
    "Overview",
    "Traces",
    "Avaliações",
    "Prompts",
    "Rubricas",
    "Datasets",
    "Experimentos",
    "Chaves API",
    "Exports",
  ]) {
    assert.match(nav, new RegExp(`label: "${label}"`));
  }

  for (const path of [
    'path: ""',
    'path: "/traces"',
    'path: "/evaluations"',
    'path: "/prompts"',
    'path: "/rubrics"',
    'path: "/datasets"',
    'path: "/experiments"',
    'path: "/keys"',
    'path: "/exports"',
  ]) {
    assert.match(nav, new RegExp(path.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  }

  assert.match(nav, /label: "Operação"/);
  assert.match(nav, /label: "Assets"/);
  assert.match(nav, /label: "Operações \/ Config"/);
  assert.match(sidebar, /aria-current=\{active \? "page" : undefined\}/);
});

test("P1 AppShell: topbar keeps real actions and marks planned alerts disabled", () => {
  assert.match(topbar, /action=\{`\/o\/\$\{org\}\/p\/\$\{project\}\/traces`\}/);
  assert.match(topbar, /name="name"/);
  assert.match(topbar, /href="\/docs"/);
  assert.match(topbar, /action=\{logoutAction\}/);
  assert.match(topbar, /data-status="planned"/);
  assert.match(topbar, /disabled/);
  assert.match(topbar, /getPageTitle/);
});

test("P1 AppShell: no preview bundle or production mock imports were added", () => {
  const combined = `${nav}\n${sidebar}\n${topbar}\n${layout}`;
  assert.doesNotMatch(combined, /data\.jsx/);
  assert.doesNotMatch(combined, /EndpointSnippet/);
  assert.doesNotMatch(combined, /evalops-preview/);
  assert.doesNotMatch(combined, /DocOps/);
  assert.doesNotMatch(combined, /Zone\.Identifier/);
});
