export type ImportedExecution = {
  id: string; project_id: string; environment: string; mode: string; status: string;
  manifest_hash: string; manifest: Record<string, unknown>; capture_origin: "external_import"; decision: null;
  attempts: { id: string; attempt_number: number; result_hash: string; result: {
    status: string; exit_reason: string; started_at: string; ended_at: string;
    prediction_set_id: string | null; trace_ids: string[]; capture_status: string;
    cost: { state: "provided" | "unknown" | "not_measured"; amount_usd: string | null; measurement_source: string | null; pricing_version: string | null };
    input_bindings: { snapshot_hash: string; prediction_hash: string | null }; producer: string; provenance: "partial";
    warnings: string[]; budget_reserved: null; decision: null;
  } }[];
};
