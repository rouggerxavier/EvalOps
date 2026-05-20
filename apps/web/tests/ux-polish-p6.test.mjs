import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const nav = readFileSync(new URL("../components/app-shell-nav.ts", import.meta.url), "utf8");
const shortcuts = readFileSync(new URL("../components/KeyboardShortcuts.tsx", import.meta.url), "utf8");
const routeError = readFileSync(new URL("../components/RouteError.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");

const loadingFiles = [
  "../app/o/[org]/p/[project]/loading.tsx",
  "../app/o/[org]/p/[project]/evaluations/loading.tsx",
  "../app/o/[org]/p/[project]/experiments/loading.tsx",
  "../app/o/[org]/p/[project]/prompts/loading.tsx",
  "../app/o/[org]/p/[project]/rubrics/loading.tsx",
  "../app/o/[org]/p/[project]/traces/loading.tsx",
  "../app/o/[org]/p/[project]/traces/[trace]/loading.tsx",
  "../app/o/[org]/p/[project]/datasets/loading.tsx",
  "../app/o/[org]/p/[project]/keys/loading.tsx",
  "../app/o/[org]/p/[project]/exports/loading.tsx",
];

const errorFiles = [
  "../app/o/[org]/p/[project]/error.tsx",
  "../app/o/[org]/p/[project]/evaluations/error.tsx",
  "../app/o/[org]/p/[project]/experiments/error.tsx",
  "../app/o/[org]/p/[project]/prompts/error.tsx",
  "../app/o/[org]/p/[project]/rubrics/error.tsx",
  "../app/o/[org]/p/[project]/traces/error.tsx",
  "../app/o/[org]/p/[project]/traces/[trace]/error.tsx",
  "../app/o/[org]/p/[project]/datasets/error.tsx",
  "../app/o/[org]/p/[project]/keys/error.tsx",
  "../app/o/[org]/p/[project]/exports/error.tsx",
];

test("P6 UX polish: every shell route exposes a unique G + letter shortcut", () => {
  const shortcutMatches = [...nav.matchAll(/shortcut: "([^"]+)"/g)].map((match) => match[1]).sort();
  assert.deepEqual(shortcutMatches, ["G D", "G E", "G K", "G O", "G P", "G R", "G S", "G T", "G X"]);
  assert.equal(new Set(shortcutMatches).size, shortcutMatches.length);
  assert.match(nav, /\{ id: "exports", label: "Exports", path: "\/exports", shortcut: "G S" \}/);
});

test("P6 UX polish: global shortcuts ignore editable focus and stale sequences", () => {
  assert.match(shortcuts, /APP_SHELL_NAV_ITEMS/);
  assert.match(shortcuts, /projectHref\(base, item\.path\)/);
  assert.match(shortcuts, /tag === "INPUT" \|\| tag === "TEXTAREA" \|\| tag === "SELECT"/);
  assert.match(shortcuts, /target\.isContentEditable/);
  assert.match(shortcuts, /event\.defaultPrevented/);
  assert.match(shortcuts, /isTypingTarget\(event\.target\)[\s\S]*armedAt\.current = 0;/);
  assert.match(shortcuts, /key === "escape"[\s\S]*armedAt\.current = 0;/);
  assert.match(shortcuts, /router\.push\(target\)/);
});

test("P6 UX polish: route error boundaries share sanitized honest error UI", () => {
  assert.match(routeError, /safeErrorMessage\(error,/);
  assert.match(routeError, /error\.digest/);
  assert.match(routeError, /reset/);
  assert.equal(/\{error\.message/.test(routeError), false);

  for (const file of errorFiles) {
    const src = readFileSync(new URL(file, import.meta.url), "utf8");
    assert.match(src, /^"use client";/);
    assert.match(src, /RouteError/);
    assert.match(src, /reset: \(\) => void/);
    assert.equal(/RefreshCw/.test(src), false, `${file} should use RouteError instead of duplicated markup`);
    assert.equal(/\{error\.message/.test(src), false);
  }
});

test("P6 UX polish: loading states expose consistent busy/live semantics", () => {
  for (const file of loadingFiles) {
    const src = readFileSync(new URL(file, import.meta.url), "utf8");
    assert.match(src, /className="evo-page" aria-busy="true" aria-live="polite"/);
    assert.match(src, /Carregando|Carregando|Recuperando|Buscando|Lendo|Resolvendo/);
  }
});

test("P6 UX polish: focus visibility and screen-reader utility are scoped to cockpit shell", () => {
  assert.match(css, /\.evo-shell \.evo-nav-item:focus-visible/);
  assert.match(css, /\.evo-shell input:focus-visible,\s*\.evo-shell select:focus-visible,\s*\.evo-shell textarea:focus-visible/);
  assert.match(css, /outline:\s*2px solid var\(--accent\)/);
  assert.match(css, /\.evo-sr-only\s*\{/);
});
