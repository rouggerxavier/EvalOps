export type Trace = {
  id: string;
  project_id: string;
  organization_id: string;
  client_trace_id?: string | null;
  name: string;
  service?: string | null;
  environment: string;
  status: "ok" | "error" | "partial";
  started_at: string;
  ended_at: string;
  duration_ms: number;
  total_tokens_in: number;
  total_tokens_out: number;
  total_cost_usd: number;
  tags: Record<string, string>;
  user_ref?: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
};

export type TraceListResponse = {
  data: Trace[];
  next_cursor: string | null;
};

export type TraceDetailResponse = {
  trace: Trace;
  spans: Array<{
    id: string;
    trace_id: string;
    parent_span_id: string | null;
    type: string;
    name: string;
    status: string;
    duration_ms: number;
    provider: string | null;
    model: string | null;
    metadata: Record<string, unknown>;
    input: Record<string, unknown> | null;
    output: Record<string, unknown> | null;
    error: Record<string, unknown> | null;
    events: Array<{
      id: string;
      type: string;
      occurred_at: string;
      payload: Record<string, unknown>;
    }>;
  }>;
  events_count: number;
};

export type OverviewResponse = {
  kpis: {
    traces: number;
    cost_usd: number;
    latency_p95_ms: number;
    avg_score: number | null;
    error_rate: number;
  };
  cost_by_day: Array<{ day: string; cost_usd: number; traces: number }>;
  model_breakdown: Array<{
    provider: string | null;
    model: string | null;
    cost_usd: number;
    tokens_in: number;
    tokens_out: number;
    calls: number;
  }>;
  recent_flagged: Trace[];
};
