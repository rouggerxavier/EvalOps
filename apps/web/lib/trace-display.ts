import type { Trace } from "./types";

const RAG_LIST_METADATA_KEYS = [
  "pipeline_version",
  "retrieved_count",
  "citation_count",
  "grounding_ok",
  "quality_level",
  "quality_score",
  "support_rate",
] as const;

const RAG_TAG_KEYS = ["pipeline", "trace_type", "kind"] as const;

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function metadataString(trace: Trace, keys: ReadonlyArray<string>): string | null {
  const metadata = isObject(trace.metadata) ? trace.metadata : {};
  for (const key of keys) {
    const value = metadata[key];
    if (typeof value === "string" && value.trim().length > 0) return value.trim();
  }
  return null;
}

function metadataNumber(trace: Trace, keys: ReadonlyArray<string>): number | null {
  const metadata = isObject(trace.metadata) ? trace.metadata : {};
  for (const key of keys) {
    const value = metadata[key];
    if (typeof value === "number" && Number.isFinite(value)) return value;
  }
  return null;
}

export function isTraceRagCandidate(trace: Trace): boolean {
  const metadata = isObject(trace.metadata) ? trace.metadata : {};
  for (const key of RAG_LIST_METADATA_KEYS) {
    if (key in metadata) return true;
  }

  for (const key of RAG_TAG_KEYS) {
    const value = trace.tags?.[key];
    if (value?.toLowerCase() === "rag") return true;
  }

  return false;
}

export function getTraceModelLabel(trace: Trace): string | null {
  return metadataString(trace, ["model", "llm_model", "model_name", "provider_model"]);
}

export function getTraceCauseLabel(trace: Trace): string | null {
  return metadataString(trace, ["error_code", "error_type", "cause", "reason_code"]);
}

export function getTraceQualityScore(trace: Trace): number | null {
  return metadataNumber(trace, ["quality_score", "aggregate_score"]);
}

export function formatTraceScore(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return value.toFixed(2);
}

export function percentile(values: number[], percentileValue: number): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const index = Math.min(sorted.length - 1, Math.max(0, Math.ceil((percentileValue / 100) * sorted.length) - 1));
  return sorted[index] ?? null;
}
