import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const traceListPage = readFileSync(
  new URL("../app/o/[org]/p/[project]/traces/page.tsx", import.meta.url),
  "utf8",
);
const traceDetailPage = readFileSync(
  new URL("../app/o/[org]/p/[project]/traces/[trace]/page.tsx", import.meta.url),
  "utf8",
);
const traceDisplay = readFileSync(new URL("../lib/trace-display.ts", import.meta.url), "utf8");
const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");

test("P2 Traces premium: list keeps server contract, cursor guard, and RAG segment", () => {
  assert.match(traceListPage, /getTraces\(\{/);
  assert.match(traceListPage, /limit:\s*50/);
  assert.match(traceListPage, /cursor:\s*qp\.cursor/);
  assert.match(traceListPage, /Pausado em página paginada/);
  assert.match(traceListPage, /<TracesAutoRefresh/);
  assert.match(traceListPage, /tabHref\("rag"\)/);
  assert.match(traceListPage, /data-testid="trace-list-rag-tab"/);
  assert.match(traceListPage, /isTraceRagCandidate/);
});

test("P2 Traces premium: list uses real trace fields and preserves planned controls", () => {
  for (const token of [
    "trace.status",
    "trace.environment",
    "trace.service",
    "trace.duration_ms",
    "trace.total_tokens_in",
    "trace.total_tokens_out",
    "trace.total_cost_usd",
    "formatDateTime(trace.created_at)",
  ]) {
    assert.match(traceListPage, new RegExp(token.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  }
  assert.match(traceListPage, /data-status="planned"/);
  assert.match(traceListPage, /disabled/);
});

test("P2 Traces premium: detail preserves UI-RAG-1, waterfall, raw metadata, and feedback", () => {
  for (const token of [
    "RAGSummaryHeader",
    "AnswerPreviewCard",
    "RetrievalSummaryCard",
    "GroundingQualityCard",
    "CitationRefsTable",
    "isRagTrace(detail)",
    'data-testid="rag-section"',
    "SpanWaterfall",
    "JSON.stringify(t.metadata, null, 2)",
    "createTraceFeedbackAction",
  ]) {
    assert.match(traceDetailPage, new RegExp(token.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  }
});

test("P2 Traces premium: planned detail actions remain disabled", () => {
  for (const label of ["Flagear", "Reexecutar", "Comparar"]) {
    assert.match(traceDetailPage, new RegExp(label));
  }
  assert.match(traceDetailPage, /data-status="planned"/);
  assert.match(traceDetailPage, /disabled/);
});

test("P2 Traces premium: CSS is scoped to trace/evo classes and responsive", () => {
  for (const selector of [
    ".evo-traces-page",
    ".evo-trace-summary",
    ".evo-traces-table-card",
    ".evo-trace-detail",
    ".evo-trace-section--rag",
    ".evo-trace-detail__bottom",
  ]) {
    assert.match(css, new RegExp(selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  }
  assert.match(css, /@media \(max-width: 760px\)[\s\S]*\.evo-trace-summary/);
  assert.doesNotMatch(css, /:root\s*\{\s*--bg-0:/);
});

test("P2 Traces premium: no preview bundle, production mock import, or app-specific RAG hardcode", () => {
  const combined = `${traceListPage}\n${traceDetailPage}\n${traceDisplay}`;
  assert.doesNotMatch(combined, /data\.jsx/);
  assert.doesNotMatch(combined, /EndpointSnippet/);
  assert.doesNotMatch(combined, /evalops-preview/);
  assert.doesNotMatch(combined, /docops/i);
  assert.doesNotMatch(combined, /Zone\.Identifier/);
});
