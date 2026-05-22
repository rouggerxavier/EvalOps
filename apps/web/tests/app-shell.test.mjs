import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const nav = readFileSync(new URL("../components/app-shell-nav.ts", import.meta.url), "utf8");
const sidebar = readFileSync(new URL("../components/Sidebar.tsx", import.meta.url), "utf8");
const topbar = readFileSync(new URL("../components/EvoTopbar.tsx", import.meta.url), "utf8");
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
    "Overview",
    "Traces",
    "Avaliacoes",
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
});

test("AppShell: sidebar footer links to /health (no static online text)", () => {
  assert.match(sidebar, /href="\/health"/);
  assert.match(sidebar, /Status do EvalOps/);
  // Bug 5.2: no hardcoded online claim survives in the shell.
  assert.doesNotMatch(sidebar, /online\s*-\s*ingestao pronta/);
});

test("AppShell: topbar keeps real actions and now exposes workspace switcher always", () => {
  assert.match(topbar, /action=\{`\$\{base\}\/traces`\}/);
  assert.match(topbar, /name="name"/);
  assert.match(topbar, /href="\/docs"/);
  assert.match(topbar, /action=\{logoutAction\}/);
  assert.match(topbar, /setEnvironmentAction/);
  assert.match(topbar, /<WorkspaceSwitcher/);
});

test("AppShell: no preview bundle imports leak into shell files", () => {
  const combined = `${nav}\n${sidebar}\n${topbar}\n${layout}`;
  assert.doesNotMatch(combined, /evalops-preview/);
  assert.doesNotMatch(combined, /EndpointSnippet/);
  assert.doesNotMatch(combined, /PreviewActionModal/);
});
