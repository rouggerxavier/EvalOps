"use client";
import { useEffect, useState } from "react";
import { useFormState, useFormStatus } from "react-dom";
import type { Investigation } from "@/lib/investigation-types";
import { saveInvestigation } from "./actions";
function Submit({ ready }: { ready: boolean }) {
  const { pending } = useFormStatus();
  return <button className="btn btn--primary" disabled={!ready || pending}>{pending ? "Salvando…" : "Salvar investigação"}</button>;
}
export function InvestigationForm({ org, project, current, environment = "dev" }: { org: string; project: string; current?: Investigation; environment?: string }) {
  const [state, action] = useFormState(saveInvestigation, {});
  const [operation, setOperation] = useState("");
  useEffect(() => setOperation(crypto.randomUUID()), [current?.revision]);
  return <form action={action} className="ops-form">
    <input type="hidden" name="org" value={org} /><input type="hidden" name="project" value={project} />
    <input type="hidden" name="id" value={current?.id ?? ""} /><input type="hidden" name="revision" value={current?.revision ?? 0} /><input type="hidden" name="operation" value={operation} />
    <label className="ops-form__field">Título<input name="title" required maxLength={255} defaultValue={current?.title} /></label>
    {current ? <p>Ambiente {current.environment} · revisão {current.revision}</p> : <label className="ops-form__field">Ambiente da investigação<select name="environment" defaultValue={environment}><option value="dev">Dev</option><option value="staging">Staging</option><option value="prod">Produção</option></select></label>}
    <label className="ops-form__field">Situação<select name="status" defaultValue={current?.status ?? "open"}><option value="open">Aberta</option><option value="resolved">Resolvida</option></select></label>
    <label className="ops-form__field">Conclusão da investigação<select name="decision" defaultValue={current?.decision ?? ""}><option value="">Sem conclusão</option><option value="inconclusive">Inconclusiva</option><option value="review">Revisão necessária</option><option value="pass">Favorável</option><option value="fail">Desfavorável</option></select></label>
    <label className="ops-form__field">Resumo técnico<textarea name="summary" maxLength={10000} defaultValue={current?.summary} rows={4} /></label>
    <label className="ops-form__field">Hipóteses (uma por linha)<textarea name="hypotheses" defaultValue={current?.hypotheses.join("\n")} rows={3} /></label>
    <label className="ops-form__field">Evidências (tipo:ID, uma por linha)<textarea name="evidence_refs" defaultValue={current?.evidence_refs.join("\n")} rows={3} placeholder="evaluation:ID ou trace:ID" /></label>
    <label className="ops-form__field">IDs de avaliações ou comparações<textarea name="run_ids" defaultValue={current?.run_ids.join("\n")} rows={2} /></label>
    <label className="ops-form__field">Próximos passos (um por linha)<textarea name="next_steps" defaultValue={current?.next_steps.join("\n")} rows={3} /></label>
    <p>Registre conclusões técnicas verificáveis. As evidências mantêm suas restrições de origem, mesmo após removidas deste editor.</p>
    {state.error && <p role="alert">{state.error}</p>}<Submit ready={!!operation} />
  </form>;
}
