import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");

test("P0: cockpit tokens are scoped to the authenticated shell", () => {
  const marker = "Refatoracao Frontend EvalOps - dashboard correto";
  const sectionStart = css.indexOf(marker);
  assert.notEqual(sectionStart, -1, "cockpit CSS section should exist");

  const cockpitSection = css.slice(sectionStart);
  assert.match(cockpitSection, /\.evo-dashboard-standalone,\s*\.evo-shell\s*\{/);
  assert.doesNotMatch(cockpitSection, /:root\s*\{\s*--bg-0:/);
});

test("P0: cockpit atmosphere is bound to evo-shell", () => {
  assert.match(css, /\.evo-shell::before,\s*\.evo-shell::after\s*\{/);
  assert.match(css, /--grid-line:\s*oklch\(/);
  assert.match(css, /background-size:\s*56px 56px/);
  assert.match(css, /mask-image:\s*linear-gradient/);
});
