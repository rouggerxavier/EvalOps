export type ImportedExecution = {
  id: string; project_id: string; environment: string; mode: string; status: string;
  manifest_hash: string; manifest: Record<string, unknown>; capture_origin: "external_import" | "controlled_runner"; control?: { plan_id: string; cancel_requested_at: string | null }; decision: null;
  attempts: { id: string; attempt_number: number; result_hash: string; result: {
    status: string; exit_reason: string; started_at: string; ended_at: string;
    prediction_set_id: string | null; trace_ids: string[]; capture_status: string;
    cost: { state: "provided" | "unknown" | "not_measured"; amount_usd: string | null; measurement_source: string | null; pricing_version: string | null };
    input_bindings: { snapshot_hash: string; prediction_hash: string | null }; producer: string; provenance: "partial";
    warnings: string[]; budget_reserved: null; decision: null;
  } }[];
};

export type ExecutionPlan = { id: string; project_id: string; environment: string; runner_id: string; manifest_hash: string; manifest: Record<string, unknown>; policy_revision_id: string; organization_budget_revision_id: string };
export type ExecutionBudget = { execution_id: string; currency: "USD"; state: string; slots_active: boolean; reserved_limit_usd: string; known_spent_usd: string | null; held_usd: string; entries: { id: string; kind: string; amount_usd: string; measurement_source: string; pricing_version: string }[] };
