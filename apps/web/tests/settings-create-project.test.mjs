import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const page = readFileSync(
  new URL("../app/o/[org]/p/[project]/settings/page.tsx", import.meta.url),
  "utf8",
);
const actions = readFileSync(new URL("../lib/actions.ts", import.meta.url), "utf8");
const api = readFileSync(new URL("../lib/api.ts", import.meta.url), "utf8");

test("settings: imports createProjectAction and renders Novo projeto card", () => {
  assert.match(page, /createProjectAction/);
  assert.match(page, /action=\{createProjectAction\}/);
  assert.match(page, /Novo projeto/);
});

test("settings: new-project form ships organization_id and the four backend fields", () => {
  // POST /v1/projects requires: organization_id, name, slug, default_environment.
  // The form must propagate org context and the user-supplied name/slug.
  assert.match(page, /name="organization_id"/);
  const newProjectFormStart = page.indexOf("action={createProjectAction}");
  assert.ok(newProjectFormStart > 0, "createProjectAction form not found");
  const newProjectForm = page.slice(newProjectFormStart, newProjectFormStart + 2800);
  assert.match(newProjectForm, /name="name"/);
  assert.match(newProjectForm, /name="slug"/);
  assert.match(newProjectForm, /name="default_environment"/);
  assert.match(newProjectForm, /pattern="\[a-z0-9-\]\+"/);
  assert.match(newProjectForm, /Criar projeto/);
});

test("settings: alerts cover updated + created", () => {
  assert.match(page, /qp\.updated \?/);
  assert.match(page, /qp\.created \?/);
  assert.match(page, /Projeto criado/);
});

test("actions: createProjectAction validates inputs and redirects to new slug settings", () => {
  assert.match(actions, /export async function createProjectAction/);
  assert.match(actions, /createProject\(/);
  assert.match(actions, /\/o\/\$\{org\}\/p\/\$\{created\.slug\}\/settings/);
  // Slug-duplicado fallback should not crash; it goes back to the error path.
  assert.match(actions, /errorMsg \?\? "Failed to create project"/);
});

test("api: createProject hits POST /projects with the right payload shape", () => {
  assert.match(api, /export async function createProject/);
  assert.match(api, /requestJson<Project>\(`\/projects`, \{[\s\S]*?method: "POST"/);
});
