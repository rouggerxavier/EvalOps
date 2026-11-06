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
  assert.match(topbar, /name="q"/);
  assert.match(topbar, /aria-label="Buscar traces"/);
  assert.doesNotMatch(topbar, /href="\/docs"/);
  assert.match(sidebar, /href="\/docs"/);
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

test("AppShell: mobile menu is a keyboard-safe drawer (item 15)", () => {
  assert.match(topbar, /aria-expanded=\{mobileMenuOpen\}/);
  assert.match(topbar, /aria-controls="ops-sidebar"/);
  assert.match(sidebar, /role=\{mobileMenuOpen \? "dialog" : undefined\}/);
  assert.match(sidebar, /className="ops-sidebar__close"[^>]*aria-label="Fechar menu"/);
  assert.match(shellFrame, /event\.key === "Escape"/);
  assert.match(shellFrame, /event\.key !== "Tab"/);
  // Closes on any route change and when the viewport grows past the drawer breakpoint.
  assert.match(shellFrame, /setMobileMenuOpen\(false\);\n  \}, \[pathname\]\);/);
  assert.match(shellFrame, /matchMedia\("\(min-width: 761px\)"\)/);
  const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");
  const mobile = css.slice(css.lastIndexOf("/* Celular (item 15)"));
  // Search, environment, notifications and logout stay reachable on a phone.
  assert.match(mobile, /\.ops-shell \.ops-topbar__search \{\n    display: block;/);
  assert.match(mobile, /\.ops-shell \.ops-topbar__right \{\n    display: contents;/);
});
