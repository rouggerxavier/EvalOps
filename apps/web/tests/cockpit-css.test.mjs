import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");

test("cockpit: shell-scoped class exists and has overlay pseudo-elements", () => {
  assert.match(css, /\.evo-shell\s*\{/);
  assert.match(css, /\.evo-shell::before/);
  assert.match(css, /\.evo-shell::after/);
});
