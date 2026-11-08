import test from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import { loadTs } from "./helpers/load-ts.mjs";

test("conversation turns have a distinct heading while existing tabs and links stay available", async () => {
  const trace = {
    id: "trace", project_id: "project", name: "Turno atual", environment: "dev", status: "ok",
    created_at: "2026-11-08T10:00:00Z", duration_ms: 10, total_cost_usd: 0,
    total_tokens_in: 0, total_tokens_out: 0, tags: {}, metadata: { conversation_id: "chat 1" },
  };
  const { default: Page } = loadTs("app/o/[org]/p/[project]/traces/[trace]/page.tsx", {
    "@/lib/api": {
      hasAuthToken: async () => true,
      getTrace: async () => ({ trace, spans: [], feedback: [], flags: [] }),
      getRubrics: async () => ({ data: [] }),
      getTraces: async () => ({ data: [trace], next_cursor: null }),
      getTraceEvaluations: async () => ({ data: [] }),
    },
    "@/lib/actions": { createTraceFeedbackAction: async () => {} },
    "./trace-actions": { TraceHeaderActions: () => null },
  });
  const html = renderToStaticMarkup(await Page({
    params: Promise.resolve({ org: "org", project: "project", trace: "trace" }), searchParams: Promise.resolve({}),
  }));
  assert.match(html, /<h[1-6][^>]*>Turnos da conversa<\/h[1-6]>/);
  assert.match(html, /href="\/o\/org\/p\/project\/traces\/trace\?tab=conversation"[^>]*>.*? Conversa<\/a>/);
  assert.match(html, /conversation_id=chat%201&amp;environment=/);
  assert.match(html, /<strong aria-current="page">Turno atual<\/strong>/);
});

test("batch form explains verdict skips and errored or partial retries beside the queue action", async () => {
  const { default: Page } = loadTs("app/o/[org]/p/[project]/rubrics/page.tsx", {
    "@/lib/api": {
      hasAuthToken: async () => true,
      resolveProject: async () => ({ project_id: "project" }),
      getRubrics: async () => ({ data: [{ id: "rubric", slug: "support", threshold: 0.7, current_version: 2, created_at: "2026-11-08T10:00:00Z" }] }),
      getCliJudges: async () => [],
      getRubricVersions: async () => ({ data: [{ id: "v1", version: 1 }, { id: "v2", version: 2 }] }),
      getRubricReport: async () => null,
    },
    "@/lib/active-env": { getActiveEnvironment: async () => "dev" },
    "@/lib/actions": { createRubricAction: "/create", createRubricVersionAction: "/version", triggerEvaluationBatchAction: "/batch" },
    "@/components/RubricYamlEditor": { RubricYamlEditor: () => null },
  });
  const html = renderToStaticMarkup(await Page({
    params: Promise.resolve({ org: "org", project: "project" }), searchParams: Promise.resolve({}),
  }));
  const batch = html.slice(html.indexOf("Avaliar em lote"));
  assert.match(batch, /Avaliações concluídas com veredito nesta rubrica e versão são ignoradas/);
  assert.match(batch, /Avaliações com erro ou parciais sem veredito podem voltar à fila e gerar novo custo/);
  assert.match(batch, /<form action="\/batch"/);
  assert.match(batch, /name="rubric_version"[^>]*><option value="2" selected=""/);
  assert.match(batch, /name="environment"[^>]*>.*<option value="dev" selected=""/);
  assert.match(batch, /name="limit" min="1" max="500" required="" value="100"/);
  assert.match(batch, /type="submit"[^>]*>Enfileirar avaliações<\/button>/);
});
