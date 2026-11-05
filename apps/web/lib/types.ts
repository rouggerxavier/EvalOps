export type ResolvedProject = {
  org_id: string;
  org_slug: string;
  org_name: string;
  project_id: string;
  project_slug: string;
  project_name: string;
};

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
  redacted: boolean;
  created_at: string;
  last_score?: number | null;
  slow_reason?: "trace" | "llm" | "retrieval" | null;
  cost_source?: "priced" | "provided" | "unpriced" | "unknown" | null;
  model?: string | null;
  flag_count?: number;
};

export type TraceListResponse = {
  data: Trace[];
  next_cursor: string | null;
};

export type TraceSpan = {
  id: string;
  trace_id: string;
  parent_span_id: string | null;
  type: string;
  name: string;
  status: string;
  started_at: string | null;
  ended_at: string | null;
  duration_ms: number;
  provider: string | null;
  model: string | null;
  tokens_in: number | null;
  tokens_out: number | null;
  cost_usd: number | null;
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
  messages_in?: Array<Record<string, unknown>> | null;
  messages_out?: Array<Record<string, unknown>> | null;
  tools?: Array<Record<string, unknown>> | null;
  prompt_version_ref?: string | null;
  fallback_from_span_id?: string | null;
};

export type TraceDetailResponse = {
  trace: Trace;
  spans: TraceSpan[];
  events_count: number;
  feedback: HumanFeedback[];
  flags: Pick<TraceFlag, "id" | "reason" | "note" | "created_at">[];
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
  last_window?: "24h" | "7d" | "30d";
};

export type Project = {
  id: string;
  organization_id: string;
  name: string;
  slug: string;
  description: string | null;
  default_environment: "dev" | "staging" | "prod";
  created_at: string;
};

export type ApiKey = {
  id: string;
  prefix: string;
  name: string;
  environment: "dev" | "staging" | "prod";
  scopes: string[];
  rate_limit_per_minute: number;
  created_at: string;
  revoked_at: string | null;
};

export type ApiKeyCreateResponse = ApiKey & {
  key: string;
};

export type Rubric = {
  id: string;
  project_id: string;
  slug: string;
  description: string | null;
  current_version: number;
  threshold: number;
  created_at: string;
};

export type RubricVersion = {
  id: string;
  rubric_id: string;
  version: number;
  yaml_source: string;
  parsed_spec: {
    evaluators?: Array<{
      id: string;
      name?: string;
      type: string;
      weight?: number;
      fail_fast?: boolean;
      enabled?: boolean;
      config?: Record<string, unknown>;
    }>;
    [key: string]: unknown;
  };
  created_by: string;
  created_at: string;
};

export type EvaluationScore = {
  id: string;
  evaluator_slug: string;
  score: number;
  passed: boolean;
  reasoning: string | null;
  raw_output: Record<string, unknown> | null;
  cost_usd: number;
  latency_ms: number;
};

export type EvaluationRun = {
  id: string;
  project_id: string;
  trace_id: string;
  rubric_id: string;
  rubric_version: number;
  triggered_by: string;
  status: string;
  aggregate_score: number | null;
  passed: boolean | null;
  cost_usd: number;
  latency_ms: number | null;
  started_at: string | null;
  completed_at: string | null;
  error: Record<string, unknown> | null;
  run_metadata: Record<string, unknown>;
  created_at: string;
  scores: EvaluationScore[];
};

export type Prompt = {
  id: string;
  project_id: string;
  slug: string;
  description: string | null;
  current_version: number;
  created_at: string;
};

export type PromptVersion = {
  id: string;
  prompt_id: string;
  version: number;
  template: string;
  variables: Record<string, unknown>;
  metadata: Record<string, unknown>;
  changelog: string | null;
  created_by: string;
  created_at: string;
};

export type Dataset = {
  id: string;
  project_id: string;
  slug: string;
  description: string | null;
  source: string;
  created_at: string;
};

export type DatasetItem = {
  id: string;
  dataset_id: string;
  ord: number;
  input: Record<string, unknown>;
  expected_output: Record<string, unknown> | null;
  metadata: Record<string, unknown>;
  created_at: string;
};

export type Experiment = {
  id: string;
  project_id: string;
  name: string;
  dataset_id: string;
  rubric_id: string;
  variants: Array<{
    name: string;
    prompt_version_ref?: string;
    model?: string;
    params?: Record<string, unknown>;
  }>;
  pass_criteria: Record<string, unknown>;
  baseline_variant: string | null;
  created_at: string;
};

export type ExperimentRun = {
  id: string;
  experiment_id: string;
  project_id: string;
  status: string;
  triggered_by: string;
  passed: boolean | null;
  by_variant: Record<string, {
    pass_rate: number;
    avg_score: number;
    avg_latency_ms: number;
    total_cost_usd: number;
    avg_cost_usd_per_item: number;
    total_items: number;
  }>;
  comparisons: Record<string, {
    delta_pass_rate: number;
    delta_cost: number;
    regression: boolean;
  }>;
  criteria_failures: string[];
  run_metadata: Record<string, unknown>;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
};

export type HumanFeedback = {
  id: string;
  trace_id: string;
  source: string;
  thumbs: "up" | "down" | null;
  rating: number | null;
  comment: string | null;
  tags: string[];
  user_ref: string | null;
  correction: Record<string, unknown> | null;
  created_at: string;
};

export type ExportJob = {
  id: string;
  project_id: string;
  status: string;
  format: "jsonl";
  filters: Record<string, unknown>;
  row_count: number;
  file_path: string | null;
  file_size_bytes: number | null;
  error: string | null;
  expires_at: string | null;
  created_by: string | null;
  created_at: string;
  completed_at: string | null;
};

export type AttentionResponse = {
  count: number;
  items: Array<{
    trace_id: string;
    cause: string;
    service: string | null;
    at: string;
  }>;
};

export type CoverageResponse = {
  data: Array<{
    rubric_id: string;
    rubric_slug: string;
    coverage: number;
    runs_7d: number;
  }>;
};

export type SdkStatus = {
  p95_ingestion_ms: number;
  spans_per_minute: number;
  last_event_at: string | null;
  services_seen: string[];
};

export type NotificationItem = {
  id: string;
  project_id: string;
  kind: string;
  title: string;
  meta: Record<string, unknown>;
  created_at: string;
  read_at: string | null;
};

export type NotificationListResponse = {
  data: NotificationItem[];
  unread_count: number;
};

export type TraceFlag = {
  id: string;
  trace_id: string;
  org_id: string;
  user_id: string;
  reason: string;
  note: string | null;
  created_at: string;
};

export type BulkTraceFlagResponse = {
  data: TraceFlag[];
  created: number;
};

export type TraceRerunResponse = {
  new_trace_id: string;
  status: string;
};

export type TraceCompareResponse = {
  left: Trace;
  right: Trace;
  diff: Record<string, unknown>;
};

export type RagConsolidated = {
  retrieved_docs: number;
  avg_score: number | null;
  grounded_claims: number;
  ungrounded_claims: number;
  hallucination_risk: "low" | "medium" | "high" | string;
  answer_preview: string | null;
  citations: Array<{
    rank: number;
    title: string | null;
    score: number | null;
    source: string | null;
    chunk: string | null;
  }>;
  claims: Array<{
    text: string;
    grounded: boolean;
    cite: string | null;
  }>;
  claim_to_chunk: Array<{
    claim: string;
    chunk: string;
    score: number | null;
  }>;
};

export type EvaluationSummary = {
  active_rubrics: number;
  runs_7d: number;
  pass_rate: number | null;
  cost_usd: number;
};

export type PromptUsage = {
  prompt_id: string;
  usage_count: number;
  traces: Array<{
    trace_id: string;
    name: string;
    service: string | null;
    environment: string;
    status: string;
    prompt_version_ref: string | null;
    used_at: string;
  }>;
};

export type ExportListResponse = {
  data: ExportJob[];
  next_cursor: string | null;
};

export type Member = {
  user_id: string;
  email: string;
  name: string;
  role: string;
  joined_at: string;
};

export type OrgSubscription = {
  organization_id: string;
  subscription: {
    id: string;
    status: string;
    started_at: string;
    ends_at: string | null;
  };
  plan: {
    id: string;
    code: string;
    name: string;
    monthly_trace_limit: number;
    monthly_eval_limit: number;
    monthly_export_limit: number;
    monthly_span_limit: number;
    monthly_token_limit: number;
    monthly_judge_budget_usd: number;
  };
};

export type OrgUsage = {
  organization_id: string;
  period: string;
  traces_ingested: number;
  evaluations_run: number;
  exports_created: number;
  spans_ingested: number;
  tokens_ingested: number;
  cost_usd: number;
};

export type QualityGateSettings = {
  min_score: number;
  max_ungrounded_rate: number;
  max_avg_cost_usd: number;
  max_p95_ms: number;
  require_zero_critical: boolean;
};

export type QualityGateConfig = QualityGateSettings & {
  project_id: string;
  configured: boolean;
  updated_at: string | null;
};

export type QualityGateState = "pass" | "review" | "fail";
export type QualityGateMetric = "configuration" | "quality" | "ungrounded" | "avg_cost" | "p95" | "critical";
export type QualityGateReason = {
  metric: QualityGateMetric;
  status: QualityGateState;
  code: string;
  observed: number | null;
  threshold: number | null;
  sample_count: number;
};

export type QualityGateStatus = {
  project_id: string;
  status: QualityGateState;
  window: "24h" | "7d" | "30d";
  environment: string | null;
  calculated_at: string;
  config: QualityGateConfig;
  metrics: {
    trace_count: number;
    evaluated_trace_count: number;
    rag_trace_count: number;
    grounding_trace_count: number;
    critical_checked_trace_count: number;
    avg_score: number | null;
    ungrounded_rate: number | null;
    avg_cost_usd: number | null;
    latency_p95_ms: number | null;
    critical_violations: number | null;
  };
  reasons: QualityGateReason[];
};
