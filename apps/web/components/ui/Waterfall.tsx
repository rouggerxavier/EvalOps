import type { TraceSpan } from "@/lib/types";

type WaterfallProps = {
  spans: TraceSpan[];
  traceDurationMs: number;
  traceStartedAt?: string;
};

function kindClass(type: string): string {
  if (["llm", "root", "retrieval", "embed", "tool", "eval"].includes(type)) return `k-${type}`;
  return "k-root";
}

function bar(span: TraceSpan, traceDurationMs: number, traceStartedAt?: string) {
  if (!traceStartedAt || !span.started_at || traceDurationMs <= 0) {
    return { left: 0, width: Math.max(1, (span.duration_ms / Math.max(traceDurationMs, 1)) * 100) };
  }
  const start = new Date(traceStartedAt).getTime();
  const spanStart = new Date(span.started_at).getTime();
  const left = Math.max(0, ((spanStart - start) / traceDurationMs) * 100);
  const width = Math.max(0.5, (span.duration_ms / traceDurationMs) * 100);
  return { left: Math.min(left, 98), width: Math.min(width, 100 - left) };
}

export function Waterfall({ spans, traceDurationMs, traceStartedAt }: WaterfallProps) {
  const ticks = [0, 0.5, 1].map((value) => `${Math.round(value * traceDurationMs)}ms`);

  return (
    <div className="waterfall">
      <div className="waterfall__scale">
        <span>Span</span>
        <span />
        <span className="waterfall__scale-line">{ticks.map((tick) => <span key={tick}>{tick}</span>)}</span>
        <span>Status</span>
      </div>
      {spans.map((span) => {
        const position = bar(span, traceDurationMs, traceStartedAt);
        return (
          <div className="waterfall__row" key={span.id}>
            <div className="waterfall__name">
              <span className="waterfall__kind">{span.type}</span>
              {span.name}
            </div>
            <div className="waterfall__duration">{span.duration_ms}ms</div>
            <div className="waterfall__bar">
              <i className={kindClass(span.type)} style={{ left: `${position.left}%`, width: `${position.width}%` }} />
            </div>
            <div className="waterfall__status">{span.status}</div>
          </div>
        );
      })}
    </div>
  );
}
