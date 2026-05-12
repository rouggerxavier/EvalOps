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
  created_at: string;
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
};

export type TraceDetailResponse = {
  trace: Trace;
  spans: TraceSpan[];
  events_count: number;
  feedback: HumanFeedback[];
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
  error: string | null;
  expires_at: string | null;
  created_by: string | null;
  created_at: string;
  completed_at: string | null;
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
  };
};

export type OrgUsage = {
  organization_id: string;
  period: string;
  traces_ingested: number;
  evaluations_run: number;
  exports_created: number;
  cost_usd: number;
};
