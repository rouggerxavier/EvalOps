import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const appShell = readFileSync(new URL("../components/OpsShellFrame.tsx", import.meta.url), "utf8");
const shortcuts = readFileSync(new URL("../components/EvoShortcuts.tsx", import.meta.url), "utf8");
const toastHost = readFileSync(new URL("../components/EvoToastHost.tsx", import.meta.url), "utf8");
const toastBridge = readFileSync(new URL("../components/EvoToastBridge.tsx", import.meta.url), "utf8");
const toastLib = readFileSync(new URL("../lib/toast.ts", import.meta.url), "utf8");
const nav = readFileSync(new URL("../components/app-shell-nav.ts", import.meta.url), "utf8");
const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");

test("P6 internal shell mounts shortcuts, toast bridge and toast host", () => {
  assert.match(appShell, /<EvoShortcuts \/>/);
  assert.match(appShell, /<EvoToastBridge \/>/);
  assert.match(appShell, /<EvoToastHost \/>/);
  assert.match(appShell, /Suspense fallback=\{null\}/);
});

test("P6 shortcut handler: only routes when prefix G is armed and target is not typing", () => {
  assert.match(shortcuts, /"use client"/);
  assert.match(shortcuts, /APP_SHELL_NAV_ITEMS/);
  assert.match(shortcuts, /isTypingTarget/);
  assert.match(shortcuts, /target\.isContentEditable/);
  assert.match(shortcuts, /role === "textbox"/);
  assert.match(shortcuts, /metaKey \|\| event\.ctrlKey \|\| event\.altKey/);
  assert.match(shortcuts, /SHORTCUT_TIMEOUT_MS/);
  assert.match(shortcuts, /router\.push\(projectHref/);
});

test("P6 shortcut map uses real nav shortcuts (G O / G T / G E / G X)", () => {
  for (const code of [/shortcut: "G O"/, /shortcut: "G T"/, /shortcut: "G E"/, /shortcut: "G X"/]) {
    assert.match(nav, code);
  }
});

test("P6 toast host listens evo:toast and renders tone-scoped items", () => {
  assert.match(toastHost, /"use client"/);
  assert.match(toastHost, /TOAST_EVENT/);
  assert.match(toastHost, /addEventListener\(TOAST_EVENT/);
  assert.match(toastHost, /removeEventListener\(TOAST_EVENT/);
  assert.match(toastHost, /evo-toast--\$\{item\.tone\}/);
  assert.match(toastHost, /aria-live="polite"/);
  assert.match(toastHost, /role=\{item\.tone === "err" \? "alert" : "status"\}/);
});

test("P6 toast bridge converts known flash params to events and strips them", () => {
  assert.match(toastBridge, /"use client"/);
  assert.match(toastBridge, /useSearchParams/);
  assert.match(toastBridge, /router\.replace/);
  for (const key of ["created", "revoked", "versioned", "feedback", "built", "items_added", "run", "error"]) {
    assert.match(toastBridge, new RegExp(`key: "${key}"`));
  }
});

test("P6 toast emit helper is SSR-safe", () => {
  assert.match(toastLib, /typeof window === "undefined"/);
  assert.match(toastLib, /CustomEvent<ToastDetail>/);
  assert.match(toastLib, /export const TOAST_EVENT = "evo:toast"/);
});

test("P6 CSS: toast styles scoped under .evo-shell", () => {
  assert.match(css, /\.evo-shell \.evo-toast-host/);
  assert.match(css, /\.evo-shell \.evo-toast \{/);
  assert.match(css, /\.evo-shell \.evo-toast--err\b/);
  assert.match(css, /@keyframes evo-toast-in/);
  // Never global, never on :root
  assert.doesNotMatch(css, /^\.evo-toast \{/m);
  assert.doesNotMatch(css, /:root \{\s*[^}]*--toast/);
});

test("P6 does not introduce AttentionStrip with invented data", () => {
  const combined = `${appShell}\n${shortcuts}\n${toastHost}\n${toastBridge}\n${toastLib}`;
  assert.doesNotMatch(combined, /AttentionStrip/);
  assert.doesNotMatch(combined, /avgScore/);
  assert.doesNotMatch(combined, /errors_7d/);
});
