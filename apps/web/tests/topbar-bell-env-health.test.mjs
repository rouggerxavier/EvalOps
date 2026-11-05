import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const bell = readFileSync(new URL("../components/ui/NotificationsBell.tsx", import.meta.url), "utf8");
const topbar = readFileSync(new URL("../components/EvoTopbar.tsx", import.meta.url), "utf8");
const shell = readFileSync(new URL("../components/AppShell.tsx", import.meta.url), "utf8");
const health = readFileSync(new URL("../app/health/page.tsx", import.meta.url), "utf8");

test("NotificationsBell exposes 'Marcar lidas' form when there are unread items", () => {
  assert.match(bell, /markNotificationsReadAction/);
  assert.match(bell, /action=\{markNotificationsReadAction\}/);
  assert.match(bell, /name="project_id"/);
  assert.match(bell, /name="current_path"/);
  // The form posts an `ids` hidden input per unread notification.
  assert.match(bell, /unread\.map[\s\S]*?name="ids"/);
  assert.match(bell, /Marcar lidas/);
});

test("EvoTopbar environment selector posts setEnvironmentAction (no purely-local state)", () => {
  assert.match(topbar, /import \{ setEnvironmentAction \}/);
  assert.match(topbar, /action=\{setEnvironmentAction\}/);
  assert.match(topbar, /name="environment"/);
  assert.match(topbar, /name="current_path"/);
  // Default value should now come from props, not useState.
  assert.match(topbar, /environment = "all"/);
  assert.doesNotMatch(topbar, /setEnvironment\(env\)/);
});

test("AppShell reads evalops_env cookie and forwards it to the topbar", () => {
  assert.match(shell, /evalops_env/);
  assert.match(shell, /cookies\(\)/);
  assert.match(shell, /environment=\{environment\}/);
});

test("/health page probes liveness + readiness against the API root", () => {
  assert.match(health, /\/health\/liveness/);
  assert.match(health, /\/health\/readiness/);
  assert.match(health, /Status do EvalOps/);
  assert.match(health, /cache: "no-store"/);
});
