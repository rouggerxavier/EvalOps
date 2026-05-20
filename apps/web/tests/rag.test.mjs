// UI-RAG-1 source-level contract tests.
//
// `package.json` ships `node --test` without a TypeScript loader, so this file
// mirrors the helper logic from `apps/web/lib/rag.ts` in plain JS and validates
// it against the fixtures under `apps/web/tests/fixtures/`. When the TS rules
// change, mirror them here so the safety net stays accurate. The mirror lives
// next to the same-named exports in `lib/rag.ts`.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const fixturesDir = resolve(__dirname, "fixtures");

function loadFixture(name) {
  return JSON.parse(readFileSync(resolve(fixturesDir, name), "utf8"));
}

// --- mirror of lib/rag.ts ---------------------------------------------------

const RAG_METADATA_KEYS = [
  "pipeline_version",
  "retrieved_count",
  "citation_count",
  "grounding_ok",
  "quality_level",
  "quality_score",
  "support_rate",
];

function isObject(v) {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function safeGet(source, path) {
  let cur = source;
  for (const key of path) {
    if (!isObject(cur)) return undefined;
    cur = cur[key];
  }
  return cur;
}

function asString(v) {
  return typeof v === "string" && v.length > 0 ? v : undefined;
}

function asNumber(v) {
  return typeof v === "number" && Number.isFinite(v) ? v : undefined;
}

function asBool(v) {
  return typeof v === "boolean" ? v : undefined;
}

function findSpan(detail, name) {
  if (!detail || !Array.isArray(detail.spans)) return undefined;
  return detail.spans.find((s) => s.name === name);
}

function isRagTrace(detail) {
  if (!detail) return false;
  const spans = detail.spans ?? [];
  for (const s of spans) {
    if (
      s.name === "rag.retrieve" ||
      s.name === "rag.grounding.validate" ||
      s.name === "response.finalize"
    ) {
      return true;
    }
  }
  const meta = detail.trace?.metadata;
  if (isObject(meta)) {
    for (const k of RAG_METADATA_KEYS) {
      if (k in meta) return true;
    }
  }
  return false;
}

function getRagSummary(detail) {
  if (!detail) return undefined;
  const t = detail.trace;
  const meta = isObject(t?.metadata) ? t.metadata : {};
  const retrieve = findSpan(detail, "rag.retrieve");
  const grounding = findSpan(detail, "rag.grounding.validate");
  const finalize = findSpan(detail, "response.finalize");
  const generate = findSpan(detail, "llm.generate");

  const model =
    asString(meta.model) ??
    asString(generate?.model) ??
    asString(detail.spans?.find((s) => asString(s.model))?.model);

  return {
    model,
    pipeline_version: asString(meta.pipeline_version),
    retrieved_count:
      asNumber(meta.retrieved_count) ?? asNumber(safeGet(retrieve?.output, ["retrieved_count"])),
    citation_count:
      asNumber(meta.citation_count) ??
      asNumber(safeGet(grounding?.output, ["citation_count"])) ??
      asNumber(safeGet(finalize?.output, ["citation_count"])),
    grounding_ok:
      asBool(meta.grounding_ok) ??
      asBool(safeGet(grounding?.output, ["grounding_ok"])) ??
      asBool(safeGet(finalize?.output, ["grounding_ok"])),
    quality_level:
      asString(meta.quality_level) ??
      asString(safeGet(grounding?.output, ["quality_level"])) ??
      asString(safeGet(finalize?.output, ["quality_level"])),
    quality_score:
      asNumber(meta.quality_score) ??
      asNumber(safeGet(grounding?.output, ["quality_score"])) ??
      asNumber(safeGet(finalize?.output, ["quality_score"])),
    strict_grounding:
      asBool(meta.strict_grounding) ??
      asBool(safeGet(retrieve?.input, ["strict_grounding"])) ??
      asBool(safeGet(grounding?.output, ["strict_grounding"])),
    has_answer:
      asBool(meta.has_answer) ?? asBool(safeGet(finalize?.output, ["has_answer"])),
    support_rate:
      asNumber(meta.support_rate) ??
      asNumber(safeGet(grounding?.output, ["support_rate"])) ??
      asNumber(safeGet(finalize?.output, ["support_rate"])),
    source_count:
      asNumber(meta.source_count) ?? asNumber(safeGet(finalize?.output, ["source_count"])),
    total_tokens_in: t?.total_tokens_in ?? 0,
    total_tokens_out: t?.total_tokens_out ?? 0,
    total_cost_usd: t?.total_cost_usd ?? 0,
    has_usage_signal:
      (t?.total_tokens_in ?? 0) > 0 ||
      (t?.total_tokens_out ?? 0) > 0 ||
      (t?.total_cost_usd ?? 0) > 0,
  };
}

function getAnswerPreview(detail) {
  if (!detail) return undefined;
  const finalize = findSpan(detail, "response.finalize");
  if (!finalize && !isObject(detail.trace?.metadata)) return undefined;
  const out = finalize?.output;
  const tmeta = isObject(detail.trace?.metadata) ? detail.trace.metadata : {};
  const a = {
    answer_preview: asString(safeGet(out, ["answer_preview"])),
    has_answer: asBool(safeGet(out, ["has_answer"])) ?? asBool(tmeta.has_answer),
    source_count: asNumber(safeGet(out, ["source_count"])) ?? asNumber(tmeta.source_count),
    citation_count:
      asNumber(safeGet(out, ["citation_count"])) ?? asNumber(tmeta.citation_count),
  };
  if (
    a.answer_preview === undefined &&
    a.has_answer === undefined &&
    a.source_count === undefined &&
    a.citation_count === undefined
  ) {
    return undefined;
  }
  return a;
}

function getRetrievalSummary(detail) {
  const retrieve = findSpan(detail, "rag.retrieve");
  if (!retrieve || !isObject(retrieve.output)) return undefined;
  const out = retrieve.output;
  return {
    retrieved_count: asNumber(out.retrieved_count),
    limit: asNumber(out.limit),
    total_available: asNumber(out.total_available),
    truncated: asBool(out.truncated),
    retrieval_mode:
      asString(safeGet(out, ["scores", "retrieval_mode"])) ?? asString(out.retrieval_mode),
    doc_refs: Array.isArray(out.doc_refs) ? out.doc_refs : undefined,
    chunk_refs: Array.isArray(out.chunk_refs) ? out.chunk_refs : undefined,
  };
}

function getGroundingQuality(detail) {
  const grounding = findSpan(detail, "rag.grounding.validate");
  const finalize = findSpan(detail, "response.finalize");
  const tmeta = isObject(detail.trace?.metadata) ? detail.trace.metadata : {};
  const sources = [grounding?.output, finalize?.output, tmeta];
  const pickBool = (k) => sources.map((s) => asBool(safeGet(s, [k]))).find((v) => v !== undefined);
  const pickNum = (k) => sources.map((s) => asNumber(safeGet(s, [k]))).find((v) => v !== undefined);
  const pickStr = (k) => sources.map((s) => asString(safeGet(s, [k]))).find((v) => v !== undefined);

  const q = {
    grounding_ok: pickBool("grounding_ok"),
    quality_level: pickStr("quality_level"),
    quality_score: pickNum("quality_score"),
    support_rate: pickNum("support_rate"),
    citation_count: pickNum("citation_count"),
    unsupported_claim_count: pickNum("unsupported_claim_count"),
    retry_count: pickNum("retry_count"),
    repair_count: pickNum("repair_count"),
  };
  const has = Object.values(q).some((v) => v !== undefined);
  return has ? q : undefined;
}

function getCitationRefs(detail) {
  const grounding = findSpan(detail, "rag.grounding.validate");
  const finalize = findSpan(detail, "response.finalize");
  const raw =
    safeGet(grounding?.output, ["citation_refs"]) ??
    safeGet(finalize?.output, ["citation_refs"]);
  if (!Array.isArray(raw) || raw.length === 0) return undefined;
  return { items: raw };
}

// --- helpers --------------------------------------------------------------

const SENSITIVE_KEYS = [
  "messages_in",
  "messages_out",
  "answer",
  "answer_text",
  "chunk_text",
  "chunk_content",
  "document_text",
  "document_content",
  "prompt_rendered",
  "api_key",
  "authorization",
  "secret",
  "token",
];

function deepScanForSensitive(node, path = []) {
  if (!node || typeof node !== "object") return [];
  const hits = [];
  if (Array.isArray(node)) {
    node.forEach((item, i) => hits.push(...deepScanForSensitive(item, [...path, String(i)])));
    return hits;
  }
  for (const [k, v] of Object.entries(node)) {
    if (SENSITIVE_KEYS.includes(k)) hits.push([...path, k].join("."));
    hits.push(...deepScanForSensitive(v, [...path, k]));
  }
  return hits;
}

// --- tests ----------------------------------------------------------------

test("RAG-01: isRagTrace true for D2 (full RAG) fixture", () => {
  const detail = loadFixture("rag-trace-d2.json");
  assert.equal(isRagTrace(detail), true);
});

test("RAG-02: isRagTrace true for D1 (no grounding) fixture", () => {
  const detail = loadFixture("rag-trace-d1.json");
  assert.equal(isRagTrace(detail), true);
});

test("RAG-03: isRagTrace true for truncated fixture", () => {
  const detail = loadFixture("rag-trace-truncated.json");
  assert.equal(isRagTrace(detail), true);
});

test("RAG-04: isRagTrace false for non-RAG fixture", () => {
  const detail = loadFixture("non-rag-trace.json");
  assert.equal(isRagTrace(detail), false);
});

test("RAG-05: getRagSummary extracts model + pipeline + counts from D2", () => {
  const summary = getRagSummary(loadFixture("rag-trace-d2.json"));
  assert.equal(summary.model, "example-model-flash");
  assert.equal(summary.pipeline_version, "rag.instrumentation.v1");
  assert.equal(summary.retrieved_count, 6);
  assert.equal(summary.citation_count, 3);
  assert.equal(summary.grounding_ok, true);
  assert.equal(summary.quality_level, "high");
  assert.equal(summary.quality_score, 0.87);
  assert.equal(summary.strict_grounding, true);
  assert.equal(summary.has_usage_signal, true);
});

test("RAG-06: getRagSummary marks zero-tokens fixture as has_usage_signal=false", () => {
  const summary = getRagSummary(loadFixture("rag-trace-zero-tokens.json"));
  assert.equal(summary.has_usage_signal, false);
  assert.equal(summary.total_tokens_in, 0);
  assert.equal(summary.total_cost_usd, 0);
});

test("RAG-07: getAnswerPreview returns preview + source_count for D2", () => {
  const a = getAnswerPreview(loadFixture("rag-trace-d2.json"));
  assert.ok(a);
  assert.equal(typeof a.answer_preview, "string");
  assert.equal(a.has_answer, true);
  assert.equal(a.source_count, 3);
});

test("RAG-08: getAnswerPreview works for D1 (no grounding)", () => {
  const a = getAnswerPreview(loadFixture("rag-trace-d1.json"));
  assert.ok(a);
  assert.equal(typeof a.answer_preview, "string");
  assert.equal(a.has_answer, true);
});

test("RAG-09: getRetrievalSummary surfaces truncation flag", () => {
  const r = getRetrievalSummary(loadFixture("rag-trace-truncated.json"));
  assert.ok(r);
  assert.equal(r.truncated, true);
  assert.equal(r.limit, 50);
  assert.equal(r.total_available, 320);
  assert.equal(r.retrieval_mode, "hybrid");
});

test("RAG-10: getRetrievalSummary undefined when no rag.retrieve span", () => {
  const r = getRetrievalSummary(loadFixture("non-rag-trace.json"));
  assert.equal(r, undefined);
});

test("RAG-11: getGroundingQuality undefined for D1 (no grounding span/metadata)", () => {
  const q = getGroundingQuality(loadFixture("rag-trace-d1.json"));
  assert.equal(q, undefined);
});

test("RAG-12: getGroundingQuality extracts retries/repair/unsupported for truncated fixture", () => {
  const q = getGroundingQuality(loadFixture("rag-trace-truncated.json"));
  assert.ok(q);
  assert.equal(q.grounding_ok, true);
  assert.equal(q.retry_count, 1);
  assert.equal(q.repair_count, 0);
  assert.equal(q.unsupported_claim_count, 2);
  assert.equal(q.quality_level, "medium");
});

test("RAG-13: getCitationRefs returns refs only (no chunk/doc text) for D2", () => {
  const c = getCitationRefs(loadFixture("rag-trace-d2.json"));
  assert.ok(c);
  assert.equal(c.items.length, 3);
  for (const item of c.items) {
    assert.equal(typeof item.fonte_n, "number");
    assert.equal(typeof item.chunk_ref, "string");
    assert.equal(typeof item.doc_ref, "string");
    assert.equal(Object.keys(item).every((k) => ["fonte_n", "chunk_ref", "doc_ref"].includes(k)), true);
  }
});

test("RAG-14: getCitationRefs undefined when no citations present", () => {
  const c = getCitationRefs(loadFixture("rag-trace-d1.json"));
  assert.equal(c, undefined);
});

test("RAG-15: helpers do not throw on empty detail", () => {
  const empty = { trace: { metadata: null }, spans: [], events_count: 0, feedback: [] };
  assert.equal(isRagTrace(empty), false);
  assert.equal(getAnswerPreview(empty), undefined);
  assert.equal(getRetrievalSummary(empty), undefined);
  assert.equal(getGroundingQuality(empty), undefined);
  assert.equal(getCitationRefs(empty), undefined);
});

test("RAG-16: helpers tolerate undefined input", () => {
  assert.equal(isRagTrace(undefined), false);
  assert.equal(isRagTrace(null), false);
  assert.equal(getRagSummary(undefined), undefined);
  assert.equal(getAnswerPreview(null), undefined);
});

test("RAG-17: fixtures do not embed sensitive raw fields", () => {
  const files = [
    "rag-trace-d2.json",
    "rag-trace-d1.json",
    "rag-trace-truncated.json",
    "rag-trace-zero-tokens.json",
    "non-rag-trace.json",
  ];
  for (const file of files) {
    const data = loadFixture(file);
    const hits = deepScanForSensitive(data);
    assert.deepEqual(hits, [], `Sensitive keys found in ${file}: ${hits.join(", ")}`);
  }
});

test("RAG-18: production code under apps/web/lib + components must not hardcode docops", () => {
  const targets = [
    "../lib/rag.ts",
    "../components/RAGSummaryHeader.tsx",
    "../components/AnswerPreviewCard.tsx",
    "../components/RetrievalSummaryCard.tsx",
    "../components/GroundingQualityCard.tsx",
    "../components/CitationRefsTable.tsx",
  ];
  for (const rel of targets) {
    const body = readFileSync(resolve(__dirname, rel), "utf8");
    assert.equal(/docops/i.test(body), false, `Found 'docops' literal in ${rel}`);
  }
});

test("RAG-19: trace detail page does not gate RAG cards on app-specific strings", () => {
  const pagePath = resolve(__dirname, "../app/o/[org]/p/[project]/traces/[trace]/page.tsx");
  const body = readFileSync(pagePath, "utf8");
  assert.equal(/docops/i.test(body), false);
  // Cards must be gated on the generic helper, not a string literal.
  assert.equal(body.includes("isRagTrace("), true);
});
