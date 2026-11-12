"use client";
import { useEffect, useState } from "react";
import { useFormState, useFormStatus } from "react-dom";
import type { TaskEvaluation } from "@/lib/task-types";
import { compareRegression } from "./actions";

function Submit() {
  const { pending } = useFormStatus();
  return <button className="btn btn--primary" disabled={pending}>{pending ? "Comparando…" : "Comparar avaliações"}</button>;
}
export function ComparisonForm({ org, project, evaluations }: { org: string; project: string; evaluations: TaskEvaluation[] }) {
  const [state, action] = useFormState(compareRegression, {});
  const [operation, setOperation] = useState("");
  useEffect(() => setOperation(crypto.randomUUID()), []);
  return <form action={action} className="form-stack">
    <input type="hidden" name="org" value={org} /><input type="hidden" name="project" value={project} /><input type="hidden" name="operation" value={operation} />
    <label>Baseline<select name="baseline" required><option value="">Selecione</option>{evaluations.map(row => <option key={row.id} value={row.id}>{row.id}</option>)}</select></label>
    <label>Candidato<select name="candidate" required><option value="">Selecione</option>{evaluations.map(row => <option key={row.id} value={row.id}>{row.id}</option>)}</select></label>
    <p>Política padrão: MAE, tolerância 0, mínimo 30 pares e cobertura 100%. Análise descritiva após observação; sem afirmação de significância.</p>
    {state.error && <p role="alert">{state.error}</p>}<Submit />
  </form>;
}
