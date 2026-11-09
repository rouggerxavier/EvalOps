import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { loadTs } from "./helpers/load-ts.mjs";

const nav = readFileSync(new URL("../components/app-shell-nav.ts", import.meta.url), "utf8");
const shortcuts = readFileSync(
  new URL("../components/EvoShortcuts.tsx", import.meta.url),
  "utf8",
);
const routeError = readFileSync(
  new URL("../components/RouteError.tsx", import.meta.url),
  "utf8",
);

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

test("UX polish: every shell route exposes a unique G + letter shortcut", () => {
  const shortcutMatches = [...nav.matchAll(/shortcut: "([^"]+)"/g)]
    .map((match) => match[1])
    .sort();
  assert.equal(
    new Set(shortcutMatches).size,
    shortcutMatches.length,
    "shortcuts must be unique",
  );
  for (const expected of ["G O", "G T", "G E", "G P", "G R", "G D", "G X", "G K", "G S"]) {
    assert.ok(shortcutMatches.includes(expected), `missing shortcut ${expected}`);
  }
});

test("UX polish: global shortcuts ignore editable focus", () => {
  assert.match(shortcuts, /APP_SHELL_NAV_ITEMS/);
  const { projectHref } = loadTs("components/app-shell-nav.ts");
  const base = "/o/org/p/project";
  assert.equal(projectHref(base, "/traces"), `${base}/traces`);
  assert.equal(projectHref(base, "/traces", ""), `${base}/traces?environment=`);
  assert.equal(projectHref(base, "/traces", "prod"), `${base}/traces?environment=prod`);
  assert.match(shortcuts, /isTypingTarget\(event\.target\)/);
});

test("UX polish: error boundaries never leak raw error.message", () => {
  assert.match(routeError, /safeErrorMessage\(error,/);
  assert.match(routeError, /error\.digest/);
  assert.match(routeError, /reset/);
  assert.doesNotMatch(routeError, /\{error\.message/);

  // The real invariant is: no raw `{error.message}` reaches the DOM. Some
  // error.tsx files use the shared `<RouteError>` helper, others render their
  // own copy — both are acceptable as long as the leak guard holds.
  for (const file of errorFiles) {
    const src = readFileSync(new URL(file, import.meta.url), "utf8");
    assert.match(src, /^"use client";/);
    assert.doesNotMatch(src, /\{error\.message/);
  }
});
