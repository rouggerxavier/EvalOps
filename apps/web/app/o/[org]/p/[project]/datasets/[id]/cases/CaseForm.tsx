"use client";
import { useEffect, useState } from "react";
import { useFormState, useFormStatus } from "react-dom";
import type { CuratedCase } from "@/lib/investigation-types";
import { classifyDataset, saveCase } from "./actions";
function Submit({ ready, label }: { ready: boolean; label: string }) {
  const { pending } = useFormStatus();
  return <button className="btn btn--primary" disabled={!ready || pending}>{pending ? "Salvando…" : label}</button>;
}
export function CaseForm({ org, project, dataset, current, trace, environment }: { org: string; project: string; dataset: string; current?: CuratedCase; trace?: { id: string; input: Record<string, unknown>; output: string }; environment: string }) {
  const [state, action] = useFormState(saveCase, {});
  const [operation, setOperation] = useState("");
  useEffect(() => setOperation(crypto.randomUUID()), [current?.revision]);
  return <form action={action} className="ops-form">
    <input type="hidden" name="org" value={org} /><input type="hidden" name="project" value={project} /><input type="hidden" name="dataset" value={dataset} />
    <input type="hidden" name="id" value={current?.id ?? ""} /><input type="hidden" name="revision" value={current?.revision ?? 0} /><input type="hidden" name="operation" value={operation} />
    <input type="hidden" name="environment" value={environment} />
    <label className="ops-form__field">ID da amostra<input name="sample_id" required maxLength={255} readOnly={!!current} defaultValue={current?.sample_id ?? trace?.id} /></label>
    <label className="ops-form__field">Entrada JSON<textarea name="input" required rows={5} defaultValue={JSON.stringify(current?.input ?? trace?.input ?? {}, null, 2)} /></label>
    <label className="ops-form__field">Referência esperada JSON<textarea name="expected_output" required rows={4} defaultValue={JSON.stringify(current?.expected_output ?? null, null, 2)} /></label>
    <label className="ops-form__field">Metadados JSON<textarea name="metadata" rows={3} defaultValue={JSON.stringify(current?.metadata ?? (trace ? { observed_output: trace.output } : {}), null, 2)} /></label>
    {current ? <><label className="ops-form__field">Estado da referência<select name="reference_status" defaultValue={current.reference_status}><option value="draft">Rascunho</option><option value="reviewed">Revisada por humano</option><option value="rejected">Rejeitada</option></select></label><label className="ops-form__field">Motivo da revisão humana<input name="review_reason" /></label></> : <label className="ops-form__field">Fontes (tipo:ID, uma por linha)<textarea name="source_refs" defaultValue={trace ? `trace:${trace.id}` : ""} rows={2} /></label>}
    <p>{current ? `Revisão ${current.revision}. Mudanças em snapshots anteriores não serão feitas.` : `Novo caso em ${environment}. Referência importada permanece em rascunho até revisão humana.`}</p>
    {state.error && <p role="alert">{state.error}</p>}<Submit ready={!!operation} label={current ? "Salvar revisão do caso" : "Salvar caso em rascunho"} />
  </form>;
}
export function ClassificationForm({ org, project, dataset, trace }: { org: string; project: string; dataset: string; trace?: string }) {
  const [state, action] = useFormState(classifyDataset, {});
  const [operation, setOperation] = useState("");
  useEffect(() => setOperation(crypto.randomUUID()), []);
  return <form action={action} className="ops-form">
    <input type="hidden" name="org" value={org} /><input type="hidden" name="project" value={project} /><input type="hidden" name="dataset" value={dataset} /><input type="hidden" name="trace" value={trace ?? ""} /><input type="hidden" name="operation" value={operation} />
    <label className="ops-form__field">Origem declarada<select name="environment" defaultValue="dev"><option value="dev">Dev</option><option value="staging">Staging</option><option value="prod">Produção</option></select></label>
    <p>Confira a origem dos itens antes de confirmar. Esta classificação inicial é auditada e não autoriza cópia entre ambientes.</p>
    {state.error && <p role="alert">{state.error}</p>}<Submit ready={!!operation} label="Classificar origem do dataset" />
  </form>;
}
