import type { TraceSpan } from "@/lib/types";
import { formatLatency } from "@/lib/format";

export function TraceSteps({
  spans,
  traceDurationMs,
  traceStartedAt,
}: {
  spans: TraceSpan[];
  traceDurationMs: number;
  traceStartedAt: string;
}) {
  if (spans.length === 0) {
    return <p className="t__empty">Sem dados de passos para este trace.</p>;
  }

  const traceStart = new Date(traceStartedAt).getTime();
  const duration = Math.max(traceDurationMs, 1);

  return (
    <div className="ops-detail__steps" aria-label={`${spans.length} passos da execução`}>
      <p className="ops-detail__steps-note">Tempo total: {formatLatency(traceDurationMs)}.</p>
      {spans.map((span) => {
        const spanStart = span.started_at ? new Date(span.started_at).getTime() : traceStart;
        const left = Math.min(99, Math.max(0, ((spanStart - traceStart) / duration) * 100));
        const width = Math.min(100 - left, Math.max(1, (span.duration_ms / duration) * 100));

        return (
          <div className="ops-detail__step-row" key={span.id}>
            <span className="ops-detail__step-name">{span.name}</span>
            <span className="ops-detail__step-track" aria-hidden="true">
              <i style={{ left: `${left}%`, width: `${width}%` }} />
            </span>
            <span className="ops-detail__step-duration">{formatLatency(span.duration_ms)}</span>
          </div>
        );
      })}
    </div>
  );
}
