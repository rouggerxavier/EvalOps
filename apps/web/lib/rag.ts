import type { TraceDetailResponse, TraceSpan } from "./types";

// Recommended RAG span names from docs/08-tracing-and-events-spec.md §9.3.
// Any application following the convention is supported; nothing here is
// app-specific.
export const RAG_SPAN_NAMES = [
  "rag.retrieve",
  "rag.context.build",
  "rag.grounding.validate",
  "response.finalize",
  "llm.generate",
] as const;

const RAG_METADATA_KEYS = [
  "pipeline_version",
  "retrieved_count",
  "citation_count",
  "grounding_ok",
  "quality_level",
  "quality_score",
  "support_rate",
] as const;

type Detail = TraceDetailResponse;
type Json = Record<string, unknown>;

function isObject(v: unknown): v is Json {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function safeGet(source: unknown, path: ReadonlyArray<string>): unknown {
  let cur: unknown = source;
  for (const key of path) {
    if (!isObject(cur)) return undefined;
    cur = cur[key];
  }
  return cur;
}

function asString(v: unknown): string | undefined {
  return typeof v === "string" && v.length > 0 ? v : undefined;
}

function asNumber(v: unknown): number | undefined {
  return typeof v === "number" && Number.isFinite(v) ? v : undefined;
}

function asBool(v: unknown): boolean | undefined {
  return typeof v === "boolean" ? v : undefined;
}

function asStringArray(v: unknown): string[] | undefined {
  if (!Array.isArray(v)) return undefined;
  const out: string[] = [];
  for (const item of v) {
    if (typeof item === "string" && item.length > 0) out.push(item);
  }
  return out.length > 0 ? out : undefined;
}

function asNumberRecord(v: unknown): Record<string, number> | undefined {
  if (!isObject(v)) return undefined;
  const out: Record<string, number> = {};
  for (const [k, val] of Object.entries(v)) {
    if (typeof val === "number" && Number.isFinite(val)) out[k] = val;
  }
  return Object.keys(out).length > 0 ? out : undefined;
}

export function findSpan(detail: Detail | null | undefined, name: string): TraceSpan | undefined {
  if (!detail || !Array.isArray(detail.spans)) return undefined;
  return detail.spans.find((s) => s.name === name);
}

export function isRagTrace(detail: Detail | null | undefined): boolean {
  if (!detail) return false;
  const spans = detail.spans ?? [];
  for (const s of spans) {
    if (s.name === "rag.retrieve" || s.name === "rag.grounding.validate" || s.name === "response.finalize") {
      return true;
    }
  }
  const meta = detail.trace?.metadata;
  if (isObject(meta)) {
    for (const key of RAG_METADATA_KEYS) {
      if (key in meta) return true;
    }
  }
  return false;
}

export type RagSummary = {
  model?: string;
  pipeline_version?: string;
  retrieved_count?: number;
  citation_count?: number;
  grounding_ok?: boolean;
  quality_level?: string;
  quality_score?: number;
  strict_grounding?: boolean;
  has_answer?: boolean;
  support_rate?: number;
  source_count?: number;
  total_tokens_in: number;
  total_tokens_out: number;
  total_cost_usd: number;
  has_usage_signal: boolean;
};

export function getRagSummary(detail: Detail | null | undefined): RagSummary | undefined {
  if (!detail) return undefined;
  const t = detail.trace;
  const meta = isObject(t?.metadata) ? (t.metadata as Json) : {};

  const retrieve = findSpan(detail, "rag.retrieve");
  const grounding = findSpan(detail, "rag.grounding.validate");
  const finalize = findSpan(detail, "response.finalize");
  const generate = findSpan(detail, "llm.generate");

  const model =
    asString(meta.model) ??
    asString(generate?.model) ??
    asString(detail.spans?.find((s) => asString(s.model))?.model);

  const pipeline_version = asString(meta.pipeline_version);

  const retrieved_count =
    asNumber(meta.retrieved_count) ?? asNumber(safeGet(retrieve?.output, ["retrieved_count"]));

  const citation_count =
    asNumber(meta.citation_count) ??
    asNumber(safeGet(grounding?.output, ["citation_count"])) ??
    asNumber(safeGet(finalize?.output, ["citation_count"]));

  const grounding_ok =
    asBool(meta.grounding_ok) ??
    asBool(safeGet(grounding?.output, ["grounding_ok"])) ??
    asBool(safeGet(finalize?.output, ["grounding_ok"]));

  const quality_level =
    asString(meta.quality_level) ??
    asString(safeGet(grounding?.output, ["quality_level"])) ??
    asString(safeGet(finalize?.output, ["quality_level"]));

  const quality_score =
    asNumber(meta.quality_score) ??
    asNumber(safeGet(grounding?.output, ["quality_score"])) ??
    asNumber(safeGet(finalize?.output, ["quality_score"]));

  const strict_grounding =
    asBool(meta.strict_grounding) ??
    asBool(safeGet(retrieve?.input, ["strict_grounding"])) ??
    asBool(safeGet(grounding?.output, ["strict_grounding"]));

  const has_answer =
    asBool(meta.has_answer) ?? asBool(safeGet(finalize?.output, ["has_answer"]));

  const support_rate =
    asNumber(meta.support_rate) ??
    asNumber(safeGet(grounding?.output, ["support_rate"])) ??
    asNumber(safeGet(finalize?.output, ["support_rate"]));

  const source_count =
    asNumber(meta.source_count) ?? asNumber(safeGet(finalize?.output, ["source_count"]));

  const total_tokens_in = t?.total_tokens_in ?? 0;
  const total_tokens_out = t?.total_tokens_out ?? 0;
  const total_cost_usd = t?.total_cost_usd ?? 0;
  const has_usage_signal = total_tokens_in > 0 || total_tokens_out > 0 || total_cost_usd > 0;

  return {
    model,
    pipeline_version,
    retrieved_count,
    citation_count,
    grounding_ok,
    quality_level,
    quality_score,
    strict_grounding,
    has_answer,
    support_rate,
    source_count,
    total_tokens_in,
    total_tokens_out,
    total_cost_usd,
    has_usage_signal,
  };
}

export type AnswerPreview = {
  answer_preview?: string;
  has_answer?: boolean;
  source_count?: number;
  citation_count?: number;
  quality_level?: string;
  quality_score?: number;
  truncated?: boolean;
};

export function getAnswerPreview(detail: Detail | null | undefined): AnswerPreview | undefined {
  if (!detail) return undefined;
  const finalize = findSpan(detail, "response.finalize");
  if (!finalize && !isObject(detail.trace?.metadata)) return undefined;

  const out = finalize?.output;
  const fmeta = finalize?.metadata;
  const tmeta = isObject(detail.trace?.metadata) ? (detail.trace.metadata as Json) : {};

  const answer_preview = asString(safeGet(out, ["answer_preview"]));
  const has_answer =
    asBool(safeGet(out, ["has_answer"])) ?? asBool(tmeta.has_answer);
  const source_count =
    asNumber(safeGet(out, ["source_count"])) ?? asNumber(tmeta.source_count);
  const citation_count =
    asNumber(safeGet(out, ["citation_count"])) ?? asNumber(tmeta.citation_count);
  const quality_level =
    asString(safeGet(out, ["quality_level"])) ?? asString(tmeta.quality_level);
  const quality_score =
    asNumber(safeGet(out, ["quality_score"])) ?? asNumber(tmeta.quality_score);
  const truncated =
    asBool(safeGet(out, ["answer_truncated"])) ??
    asBool(safeGet(fmeta, ["answer_truncated"])) ??
    asBool(safeGet(out, ["truncated"]));

  if (
    answer_preview === undefined &&
    has_answer === undefined &&
    source_count === undefined &&
    citation_count === undefined
  ) {
    return undefined;
  }

  return {
    answer_preview,
    has_answer,
    source_count,
    citation_count,
    quality_level,
    quality_score,
    truncated,
  };
}

export type ChunkRef = {
  chunk_ref?: string;
  doc_ref?: string;
  score?: number;
};

export type RetrievalSummary = {
  retrieved_count?: number;
  limit?: number;
  total_available?: number;
  truncated?: boolean;
  retrieval_mode?: string;
  doc_refs?: string[];
  chunk_refs?: ChunkRef[];
};

function normalizeChunkRefs(v: unknown): ChunkRef[] | undefined {
  if (!Array.isArray(v)) return undefined;
  const out: ChunkRef[] = [];
  for (const item of v) {
    if (typeof item === "string") {
      out.push({ chunk_ref: item });
      continue;
    }
    if (!isObject(item)) continue;
    out.push({
      chunk_ref: asString(item.chunk_ref) ?? asString(item.id) ?? asString(item.ref),
      doc_ref: asString(item.doc_ref) ?? asString(item.source) ?? asString(item.document_ref),
      score: asNumber(item.score),
    });
  }
  return out.length > 0 ? out : undefined;
}

export function getRetrievalSummary(detail: Detail | null | undefined): RetrievalSummary | undefined {
  if (!detail) return undefined;
  const retrieve = findSpan(detail, "rag.retrieve");
  if (!retrieve) return undefined;
  const out = retrieve.output;
  if (!isObject(out)) return undefined;

  const retrieval_mode =
    asString(safeGet(out, ["scores", "retrieval_mode"])) ??
    asString(safeGet(out, ["retrieval_mode"])) ??
    asString(safeGet(retrieve.metadata, ["retrieval_mode"]));

  const doc_refs = asStringArray(out.doc_refs);
  const chunk_refs = normalizeChunkRefs(out.chunk_refs);

  const summary: RetrievalSummary = {
    retrieved_count: asNumber(out.retrieved_count),
    limit: asNumber(out.limit),
    total_available: asNumber(out.total_available),
    truncated: asBool(out.truncated),
    retrieval_mode,
    doc_refs,
    chunk_refs,
  };
  return summary;
}

export type GroundingQuality = {
  grounding_ok?: boolean;
  quality_level?: string;
  quality_score?: number;
  support_rate?: number;
  citation_count?: number;
  unsupported_claim_count?: number;
  retry_count?: number;
  repair_count?: number;
  strict_grounding?: boolean;
  quality_reason_codes?: string[];
  quality_components?: Record<string, number>;
};

export function getGroundingQuality(detail: Detail | null | undefined): GroundingQuality | undefined {
  if (!detail) return undefined;
  const grounding = findSpan(detail, "rag.grounding.validate");
  const finalize = findSpan(detail, "response.finalize");
  const tmeta = isObject(detail.trace?.metadata) ? (detail.trace.metadata as Json) : {};

  const sources: unknown[] = [grounding?.output, finalize?.output, tmeta];

  function pickString(key: string): string | undefined {
    for (const src of sources) {
      const v = asString(safeGet(src, [key]));
      if (v !== undefined) return v;
    }
    return undefined;
  }

  function pickNumber(key: string): number | undefined {
    for (const src of sources) {
      const v = asNumber(safeGet(src, [key]));
      if (v !== undefined) return v;
    }
    return undefined;
  }

  function pickBool(key: string): boolean | undefined {
    for (const src of sources) {
      const v = asBool(safeGet(src, [key]));
      if (v !== undefined) return v;
    }
    return undefined;
  }

  const quality_reason_codes =
    asStringArray(safeGet(grounding?.output, ["quality_reason_codes"])) ??
    asStringArray(safeGet(finalize?.output, ["quality_reason_codes"])) ??
    asStringArray(tmeta.quality_reason_codes);

  const quality_components =
    asNumberRecord(safeGet(grounding?.output, ["quality_components"])) ??
    asNumberRecord(safeGet(finalize?.output, ["quality_components"])) ??
    asNumberRecord(tmeta.quality_components);

  const q: GroundingQuality = {
    grounding_ok: pickBool("grounding_ok"),
    quality_level: pickString("quality_level"),
    quality_score: pickNumber("quality_score"),
    support_rate: pickNumber("support_rate"),
    citation_count: pickNumber("citation_count"),
    unsupported_claim_count: pickNumber("unsupported_claim_count"),
    retry_count: pickNumber("retry_count"),
    repair_count: pickNumber("repair_count"),
    strict_grounding: pickBool("strict_grounding"),
    quality_reason_codes,
    quality_components,
  };

  const hasSignal = Object.values(q).some((v) => v !== undefined);
  return hasSignal ? q : undefined;
}

export type CitationRef = {
  fonte_n?: number;
  chunk_ref?: string;
  doc_ref?: string;
};

export type CitationRefs = {
  items: CitationRef[];
  limit?: number;
  total_available?: number;
  truncated?: boolean;
};

function normalizeCitations(v: unknown): CitationRef[] | undefined {
  if (!Array.isArray(v)) return undefined;
  const out: CitationRef[] = [];
  for (const item of v) {
    if (!isObject(item)) continue;
    out.push({
      fonte_n: asNumber(item.fonte_n) ?? asNumber(item.n) ?? asNumber(item.index),
      chunk_ref:
        asString(item.chunk_ref) ?? asString(item.chunk_id) ?? asString(item.ref),
      doc_ref:
        asString(item.doc_ref) ?? asString(item.source) ?? asString(item.document_ref),
    });
  }
  return out.length > 0 ? out : undefined;
}

export function getCitationRefs(detail: Detail | null | undefined): CitationRefs | undefined {
  if (!detail) return undefined;
  const grounding = findSpan(detail, "rag.grounding.validate");
  const finalize = findSpan(detail, "response.finalize");

  const items =
    normalizeCitations(safeGet(grounding?.output, ["citation_refs"])) ??
    normalizeCitations(safeGet(finalize?.output, ["citation_refs"])) ??
    normalizeCitations(safeGet(grounding?.output, ["citations"])) ??
    normalizeCitations(safeGet(finalize?.output, ["citations"]));

  if (!items || items.length === 0) return undefined;

  const limit =
    asNumber(safeGet(grounding?.output, ["limit"])) ??
    asNumber(safeGet(finalize?.output, ["limit"]));
  const total_available =
    asNumber(safeGet(grounding?.output, ["total_available"])) ??
    asNumber(safeGet(finalize?.output, ["total_available"]));
  const truncated =
    asBool(safeGet(grounding?.output, ["truncated"])) ??
    asBool(safeGet(finalize?.output, ["truncated"]));

  return { items, limit, total_available, truncated };
}

export function shortRef(value: string | undefined, head = 8): string {
  if (!value) return "—";
  if (value.length <= head + 2) return value;
  return `${value.slice(0, head)}…`;
}

export function formatScore(value: number | undefined, digits = 2): string {
  if (value === undefined) return "—";
  return value.toFixed(digits);
}
