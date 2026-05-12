"use client";

import { useState } from "react";
import type { TraceSpan } from "@/lib/types";

type Props = {
  spans: TraceSpan[];
  traceDurationMs: number;
  traceStartedAt: string;
};

type KindStyle = { color: string; bg: string; label: string };

const KIND_STYLES: Record<string, KindStyle> = {
  llm:       { color: "var(--accent)",  bg: "rgba(79,140,255,0.22)",   label: "llm" },
  retrieval: { color: "var(--eval)",    bg: "rgba(167,139,250,0.22)",  label: "retr" },
  tool:      { color: "var(--ok)",      bg: "rgba(34,211,168,0.22)",   label: "tool" },
  function:  { color: "var(--warn)",    bg: "rgba(240,183,66,0.22)",   label: "fn" },
  root:      { color: "var(--text-muted)", bg: "var(--surface-2)",     label: "root" },
  default:   { color: "var(--text-dim)", bg: "var(--surface-2)",       label: "span" },
};

function kindStyle(type: string): KindStyle {
  return KIND_STYLES[type] ?? KIND_STYLES.default;
}

function buildTree(spans: TraceSpan[]): { span: TraceSpan; depth: number }[] {
  const byParent: Record<string, TraceSpan[]> = {};
  for (const s of spans) {
    const key = s.parent_span_id ?? "__root__";
    (byParent[key] ??= []).push(s);
  }
  const result: { span: TraceSpan; depth: number }[] = [];
  function walk(parentId: string, depth: number) {
    for (const s of byParent[parentId] ?? []) {
      result.push({ span: s, depth });
      walk(s.id, depth + 1);
    }
  }
  walk("__root__", 0);
  return result.length > 0 ? result : spans.map((s) => ({ span: s, depth: 0 }));
}

function spanBar(span: TraceSpan, traceDurationMs: number, traceStartedAt: string) {
  if (!span.started_at || traceDurationMs <= 0) {
    const w = Math.max(2, (span.duration_ms / Math.max(traceDurationMs, 1)) * 100);
    return { off: 0, w };
  }
  const traceStart = new Date(traceStartedAt).getTime();
  const spanStart = new Date(span.started_at).getTime();
  const off = Math.max(0, ((spanStart - traceStart) / traceDurationMs) * 100);
  const w = Math.max(0.5, (span.duration_ms / traceDurationMs) * 100);
  return { off: Math.min(off, 98), w: Math.min(w, 100 - off) };
}

function JsonView({ value }: { value: unknown }) {
  if (value === null || value === undefined) {
    return <span style={{ color: "var(--text-faint)", fontStyle: "italic" }}>—</span>;
  }
  const raw = JSON.stringify(value, null, 2);
  return (
    <div className="evo-code" style={{ maxHeight: 280 }}>
      <div className="evo-code__header">JSON</div>
      <pre className="evo-code__body" style={{ maxHeight: 240, overflowY: "auto", margin: 0 }}>{raw}</pre>
    </div>
  );
}

export function SpanWaterfall({ spans, traceDurationMs, traceStartedAt }: Props) {
  const tree = buildTree(spans);
  const [selectedId, setSelectedId] = useState<string>(tree[0]?.span.id ?? "");

  const selectedEntry = tree.find((e) => e.span.id === selectedId);
  const sel = selectedEntry?.span;

  const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => ({
    pct: t * 100,
    label: `${Math.round(t * traceDurationMs)}ms`,
  }));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-3)" }}>
      {/* Waterfall */}
      <div className="evo-waterfall">
        {/* Axis */}
        <div className="evo-waterfall__axis">
          <div className="evo-waterfall__axis-label">Span</div>
          <div className="evo-waterfall__axis-ruler" style={{ height: 18 }}>
            {ticks.map((t) => (
              <span
                key={t.pct}
                className="evo-waterfall__tick"
                style={{
                  left: `${t.pct}%`,
                  transform: t.pct === 0 ? "translateX(0)" : t.pct === 100 ? "translateX(-100%)" : "translateX(-50%)",
                }}
              >
                {t.label}
              </span>
            ))}
          </div>
        </div>

        {/* Rows */}
        {tree.map(({ span, depth }, i) => {
          const { off, w } = spanBar(span, traceDurationMs, traceStartedAt);
          const ks = kindStyle(span.type);
          const isSel = span.id === selectedId;

          return (
            <div
              key={span.id}
              className={`evo-waterfall__row ${isSel ? "is-selected" : ""}`}
              onClick={() => setSelectedId(span.id)}
            >
              <div className="evo-waterfall__name" style={{ paddingLeft: 20 + depth * 16 }}>
                {depth > 0 && (
                  <span style={{ color: "var(--text-faint)", fontFamily: "var(--font-evo-mono)", fontSize: 10 }}>└</span>
                )}
                <span
                  className="evo-waterfall__type-chip"
                  style={{ background: ks.bg, color: ks.color }}
                >
                  {ks.label}
                </span>
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {span.name}
                </span>
                {span.status !== "ok" && (
                  <span className={`evo-dot evo-dot--${span.status === "error" ? "err" : "warn"}`} />
                )}
              </div>

              <div className="evo-waterfall__bar-area" style={{ position: "relative", height: 20 }}>
                <div
                  className="evo-waterfall__bar"
                  style={{
                    left: `${off}%`,
                    width: `${w}%`,
                    background: ks.color,
                    opacity: span.status === "error" ? 1 : 0.85,
                    animation: `bar-grow 600ms ${i * 40}ms cubic-bezier(0.16, 1, 0.3, 1) backwards`,
                  }}
                >
                  {w > 8 && (
                    <span className="evo-waterfall__bar-label">{span.duration_ms}ms</span>
                  )}
                </div>
                {w <= 8 && (
                  <span
                    className="evo-waterfall__bar-labelout"
                    style={{ left: `calc(${off + w}% + 4px)` }}
                  >
                    {span.duration_ms}ms
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Selected span detail */}
      {sel && (
        <div className="evo-span-detail">
          <div className="evo-card">
            <div className="evo-card__header">
              <div>
                <h3 className="evo-card__title">{sel.name}</h3>
                <div className="evo-card__subtitle">
                  {sel.type}
                  {sel.provider ? ` · ${sel.provider}` : ""}
                  {sel.model ? ` · ${sel.model}` : ""}
                  {` · ${sel.duration_ms}ms`}
                  {sel.tokens_in != null ? ` · ${sel.tokens_in}↓ ${sel.tokens_out ?? 0}↑ tok` : ""}
                </div>
              </div>
              <span
                className={`evo-badge evo-badge--${sel.status === "ok" ? "ok" : sel.status === "error" ? "err" : "warn"}`}
              >
                <span className="evo-badge__dot" />
                {sel.status}
              </span>
            </div>
            <div className="evo-card__body">
              <div style={{ fontSize: 11, color: "var(--text-faint)", textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 8 }}>
                Input
              </div>
              <JsonView value={sel.input} />
            </div>
          </div>

          <div className="evo-card">
            <div className="evo-card__header">
              <h3 className="evo-card__title">
                {sel.error ? "Erro" : "Output"}
              </h3>
            </div>
            <div className="evo-card__body">
              <div style={{ fontSize: 11, color: "var(--text-faint)", textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 8 }}>
                {sel.error ? "Error payload" : "Output"}
              </div>
              <JsonView value={sel.error ?? sel.output} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
