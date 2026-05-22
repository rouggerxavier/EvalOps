import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const page = readFileSync(
  new URL("../app/o/[org]/p/[project]/page.tsx", import.meta.url),
  "utf8",
);

function escaped(token) {
  return new RegExp(token.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
}

test("overview premium: uses real frontend data sources", () => {
  for (const token of [
    "getOverview(projectId, environment, window_)",
    "getRubrics(projectId)",
    "resolveProject(org, project)",
    "kpis.error_rate",
    "kpis.cost_usd",
  ]) {
    assert.match(page, escaped(token));
  }
});

test("overview premium: keeps links to real app-shell routes", () => {
  for (const route of ["/traces"]) {
    assert.match(page, escaped(`/o/${"${org}"}/p/${"${project}"}${route}`));
  }
});

test("overview premium: avoids preview/mock leakage", () => {
  assert.doesNotMatch(page, /evalops-preview/);
  assert.doesNotMatch(page, /EndpointSnippet/);
  assert.doesNotMatch(page, /PreviewActionModal/);
  assert.doesNotMatch(page, /Math\.random/);
});
