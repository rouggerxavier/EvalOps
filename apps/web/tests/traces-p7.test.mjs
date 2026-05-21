import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const listPage = readFileSync(
  new URL("../app/o/[org]/p/[project]/traces/page.tsx", import.meta.url),
  "utf8",
);
const detailPage = readFileSync(
  new URL("../app/o/[org]/p/[project]/traces/[trace]/page.tsx", import.meta.url),
  "utf8",
);
const filterBar = readFileSync(
  new URL("../components/TracesFilterBar.tsx", import.meta.url),
  "utf8",
);
const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");

test("P7.7 traces list: server contract + cursor guard + auto-refresh preserved", () => {
  assert.match(listPage, /getTraces\(\{/);
  assert.match(listPage, /limit:\s*50/);
  assert.match(listPage, /cursor:\s*qp\.cursor/);
  assert.match(listPage, /Pausado em página paginada/);
  assert.match(listPage, /<TracesAutoRefresh/);
  assert.match(listPage, /enabledByDefault=\{autoRefreshEnabled\}/);
});

test("P7.7 traces list: header re-tune (ao vivo pill + ZIP-voice subtitle)", () => {
  assert.match(listPage, /data-testid="trace-list-live-pill"/);
  assert.match(listPage, /evo-traces-live/);
  assert.match(listPage, /ao vivo/);
  assert.match(listPage, /auto-refresh a cada 30s/);
  assert.match(listPage, /\{rows\.length\.toLocaleString\("pt-BR"\)\} trace/);
});

test("P7.7 traces list: RAG tab keeps testid + gains Layers icon", () => {
  assert.match(listPage, /import \{[^}]*Layers[^}]*\} from "lucide-react"/);
  assert.match(listPage, /data-testid="trace-list-rag-tab"/);
  assert.match(listPage, /<Layers size=\{12\} \/> RAG/);
  assert.match(listPage, /isTraceRagCandidate/);
});

test("P7.7 traces list: planned controls + real data preserved (no invented metrics)", () => {
  for (const token of [
    "trace.status",
    "trace.environment",
    "trace.duration_ms",
    "trace.total_tokens_in",
    "trace.total_tokens_out",
    "trace.total_cost_usd",
    "formatDateTime(trace.created_at)",
  ]) {
    assert.match(listPage, new RegExp(token.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  }
  assert.match(listPage, /data-status="planned"/);
  assert.match(listPage, /Seleção em lote — em breve/);
  assert.doesNotMatch(listPage, /avgScore/);
  assert.doesNotMatch(listPage, /errors_7d/);
});

test("P7.7 traces detail: RAG segment (UI-RAG-1) + waterfall + metadata + feedback preserved", () => {
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
    assert.match(detailPage, new RegExp(token.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  }
});

test("P7.7 traces detail: flat layout (no tabs, no PreviewActionModal)", () => {
  assert.doesNotMatch(detailPage, /PreviewActionModal/);
  assert.doesNotMatch(detailPage, /useState/);
  assert.doesNotMatch(detailPage, /setTab\(/);
  assert.doesNotMatch(detailPage, /tab === "rag"/);
  assert.doesNotMatch(detailPage, /tab === "waterfall"/);
  assert.doesNotMatch(detailPage, /tab === "metadata"/);
  assert.doesNotMatch(detailPage, /tab === "feedback"/);
});

test("P7.7 traces detail: header re-tune (mono title + back eyebrow + 4 planned actions)", () => {
  assert.match(detailPage, /evo-trace-detail__title/);
  assert.match(detailPage, /evo-page-header__title evo-mono/);
  assert.match(detailPage, /evo-trace-detail__back/);
  assert.match(detailPage, /← Traces/);
  for (const label of ["Flagear", "Reexecutar", "Comparar", "Avaliar"]) {
    assert.match(detailPage, new RegExp(label));
  }
  assert.match(detailPage, /import \{[^}]*Target[^}]*\} from "lucide-react"/);
  assert.match(detailPage, /data-status="planned"/);
});

test("P7.7 traces detail: KPI hints carry ZIP voice", () => {
  assert.match(detailPage, /hint="prompt"/);
  assert.match(detailPage, /hint="completion"/);
  assert.match(detailPage, /hint="capturados"/);
  assert.match(detailPage, /hint="tempo total"/);
});

test("P7.7 CSS: new primitives scoped to .evo-shell + no token leakage", () => {
  assert.match(css, /\.evo-shell \.evo-traces-live \{/);
  assert.match(css, /\.evo-shell \.evo-trace-detail__title \{/);
  assert.match(css, /\.evo-shell \.evo-trace-detail__back \{/);
  assert.match(css, /\.evo-traces-page/);
  assert.match(css, /\.evo-trace-detail/);
  assert.doesNotMatch(css, /:root\s*\{\s*--bg-0:/);
});

test("P7.7 traces: no ZIP mock leakage in any traces surface", () => {
  const combined = `${listPage}\n${detailPage}\n${filterBar}`;
  assert.doesNotMatch(combined, /evalops-preview/);
  assert.doesNotMatch(combined, /data\.jsx/);
  assert.doesNotMatch(combined, /window\.TRACES/);
  assert.doesNotMatch(combined, /PreviewPill/);
  assert.doesNotMatch(combined, /Funcionalidade preservada/);
});
