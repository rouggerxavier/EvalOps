import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { loadTs } from "./helpers/load-ts.mjs";

const { TraceEvaluations } = loadTs("app/o/[org]/p/[project]/traces/[trace]/trace-evaluations.tsx");
const run = (overrides = {}) => ({
  id: "run-1", rubric_id: "rubric-1", rubric_version: 1, status: "completed",
  passed: true, aggregate_score: 1, cost_usd: 0.01, triggered_by: "manual",
  created_at: "2026-11-08T10:00:00Z", run_metadata: {}, error: null,
  scores: [{ id: "score-1", evaluator_slug: "judge", passed: true, score: 1,
    reasoning: "Resposta correta", cost_usd: 0.01, raw_output: {} }],
  ...overrides,
});
const render = (runs) => renderToStaticMarkup(React.createElement(TraceEvaluations, {
  runs, rubrics: [{ id: "rubric-1", slug: "atendimento" }],
}));

test("evaluation history keeps failed runs without scores beside later successful runs", () => {
  const html = render([
    run({ id: "old", rubric_version: 2, status: "error", passed: null,
      aggregate_score: null, scores: [], created_at: "2026-11-07T10:00:00Z",
      error: { reasons: ["judge_key_not_configured:openai"] } }),
    run(),
  ]);
  assert.match(html, /atendimento v2/);
  assert.match(html, /Configure openai na API para usar este juiz/);
  assert.match(html, /erro/);
  assert.match(html, /Resposta correta/);
});

test("partial verdict and critical flags survive independently of individual scores", () => {
  const html = render([run({ passed: null, aggregate_score: 0.9,
    run_metadata: { partial_failure: true, raised_flags: ["privacy"] },
    scores: [{ id: "partial", evaluator_slug: "judge", passed: true, score: 0.9,
      reasoning: "Resposta parcial", cost_usd: 0.01,
      raw_output: { flags: ["pii"], samples: [0.8, 1], stddev: 0.1 } }],
  })]);
  assert.match(html, /sem veredito/);
  assert.match(html, /A nota cobre só o restante/);
  assert.match(html, /Flag crítica levantada: privacy/);
  assert.match(html, /pii/);
  assert.match(html, /2 amostras/);
  assert.match(html, /desvio 0.10/);
});
