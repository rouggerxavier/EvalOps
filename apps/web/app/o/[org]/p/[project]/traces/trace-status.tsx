import { AlertTriangle, CheckCircle2, CircleX, HelpCircle } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import type { EvaluationRun } from "@/lib/types";

export type EvaluationVerdict = "approved" | "partial" | "rejected" | "unknown";

export function evaluationVerdict(run: EvaluationRun | undefined): EvaluationVerdict | null {
  if (!run) return null;
  if (run.passed === true) return "approved";
  if (run.passed === false) return "rejected";
  if (run.run_metadata.partial_failure === true) return "partial";
  return "unknown";
}

const VERDICTS: Record<EvaluationVerdict, { label: string; Icon: LucideIcon }> = {
  approved: { label: "Aprovado", Icon: CheckCircle2 },
  partial: { label: "Parcial", Icon: AlertTriangle },
  rejected: { label: "Reprovado", Icon: CircleX },
  unknown: { label: "Sem dados", Icon: HelpCircle },
};

export function EvaluationStatus({ verdict }: { verdict: EvaluationVerdict | null }) {
  if (!verdict) {
    return (
      <span className="ops-status ops-status--unknown">
        <HelpCircle size={13} aria-hidden="true" />
        Sem dados
      </span>
    );
  }

  const { label, Icon } = VERDICTS[verdict];
  return (
    <span className={`ops-status ops-status--${verdict}`}>
      <Icon size={13} aria-hidden="true" />
      {label}
    </span>
  );
}

export function GroundingStatus({ grounded }: { grounded: boolean }) {
  const Icon = grounded ? CheckCircle2 : CircleX;
  return (
    <span className={`ops-status ops-status--${grounded ? "approved" : "rejected"}`}>
      <Icon size={13} aria-hidden="true" />
      {grounded ? "Com fonte" : "Sem fonte"}
    </span>
  );
}
