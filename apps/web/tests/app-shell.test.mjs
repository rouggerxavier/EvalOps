import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const nav = readFileSync(new URL("../components/app-shell-nav.ts", import.meta.url), "utf8");
const sidebar = readFileSync(new URL("../components/Sidebar.tsx", import.meta.url), "utf8");
const topbar = readFileSync(new URL("../components/EvoTopbar.tsx", import.meta.url), "utf8");
const shellFrame = readFileSync(new URL("../components/OpsShellFrame.tsx", import.meta.url), "utf8");
const layout = readFileSync(
  new URL("../app/o/[org]/p/[project]/layout.tsx", import.meta.url),
  "utf8",
);

test("AppShell: authenticated layout mounts the scoped shell", () => {
  assert.match(layout, /import \{ AppShell \}/);
  assert.match(layout, /<AppShell org=\{org\} project=\{project\} initials=\{initials\}>/);
});

test("AppShell: sidebar nav preserves real project modules and routes", () => {
  for (const label of [
    "Visão geral",
    "Traces",
    "Avaliações",
    "Prompts",
    "Rubricas",
    "Datasets",
    "Experimentos",
    "Chaves de API",
    "Exports",
    "Ajustes",
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
});

test("AppShell: sidebar shows real operational counts and omits public status links", () => {
  assert.match(sidebar, /<WorkspaceSwitcher/);
  assert.match(sidebar, /attentionCount/);
  assert.match(sidebar, /Traces no mês/);
  assert.doesNotMatch(sidebar, /href="\/health"/);
  // No hardcoded health claim survives in the app shell.
  assert.doesNotMatch(sidebar, /online\s*-\s*ingestao pronta/);
});

test("AppShell: topbar keeps real actions and limits search to traces", () => {
  assert.match(topbar, /action=\{`\$\{base\}\/traces`\}/);
  assert.match(topbar, /name="name"/);
  assert.match(topbar, /Buscar traces pelo nome/);
  assert.doesNotMatch(topbar, /href="\/docs"/);
  assert.match(topbar, /action=\{logoutAction\}/);
  assert.match(topbar, /setEnvironmentAction/);
  assert.match(shellFrame, /ops-menu-backdrop/);
  assert.match(shellFrame, /ops-menu-open/);
});

test("AppShell: no preview bundle imports leak into shell files", () => {
  const combined = `${nav}\n${sidebar}\n${topbar}\n${shellFrame}\n${layout}`;
  assert.doesNotMatch(combined, /evalops-preview/);
  assert.doesNotMatch(combined, /EndpointSnippet/);
  assert.doesNotMatch(combined, /PreviewActionModal/);
});
