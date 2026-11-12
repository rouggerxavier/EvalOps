export type InvestigationState = {
  title: string; status: "open" | "resolved"; summary: string; hypotheses: string[];
  evidence_refs: string[]; run_ids: string[]; next_steps: string[];
  decision: "pass" | "fail" | "review" | "inconclusive" | null;
};
export type Investigation = InvestigationState & {
  id: string; project_id: string; environment: string; revision: number;
  author_kind: "human" | "service"; author_id: string; updated_at: string;
};
export type CuratedCase = {
  id: string; dataset_id: string; sample_id: string; input: Record<string, unknown>;
  expected_output: Record<string, unknown> | null; metadata: Record<string, unknown>;
  reference_status: "draft" | "reviewed" | "rejected"; revision: number;
};
