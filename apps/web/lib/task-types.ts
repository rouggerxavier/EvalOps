export type TaskEvaluation = {
  schema_version: 1; kind: "task_evaluation"; id: string; project_id: string;
  prediction_set_id: string; snapshot_id: string; environment: string; status: string;
  decision: "pass" | "fail" | "review" | "inconclusive" | null; decision_reasons: string[];
  n_total: number; n_valid: number; coverage: number | null; created_at: string;
  evaluator_manifest: { id: string; version: string }; config_hash: string;
};
export type MetricFact = {
  id: string; definition_id: string; definition_version: string; scope: string; scope_key: string;
  value_type: "scalar" | "series" | "matrix"; value: number | { points: { key: string; x: number; y: number | null; state: string; reason: string | null }[] } | { row_axis: { labels: string[] }; column_axis: { labels: string[] }; cells: number[][] } | null;
  averaging?: string | null; class_label?: string | null; statistics?: Record<string, { value: number; unit: string }>;
  unit: string; state: string; reason: string | null; n_total: number; n_valid: number; coverage: number | null;
};

export const taskDecisionLabels = { pass: "Aprovado pela política", fail: "Reprovado pela política", review: "Revisão necessária", inconclusive: "Inconclusivo" };
