"use client";
import { useEffect, useState } from "react";
import { useFormState, useFormStatus } from "react-dom";
import { planOperation } from "./actions";
function Submit({ ready, label }: { ready: boolean; label: string }) {
  const { pending } = useFormStatus();
  return <button className="btn btn--primary" disabled={!ready || pending}>{pending ? "Salvando…" : label}</button>;
}
export function PlanForm({ org, project, intent = "plan", id }: { org: string; project: string; intent?: "plan" | "enqueue" | "cancel"; id?: string }) {
  const [state, action] = useFormState(planOperation, {});
  const [operation, setOperation] = useState("");
  const [payload, setPayload] = useState("");
  const [error, setError] = useState("");
  useEffect(() => setOperation(crypto.randomUUID()), []);
  async function upload(file?: File) {
    if (!file) return;
    if (file.size > 10 * 1024 * 1024) { setError("Arquivo excede 10 MiB."); return; }
    setPayload(await file.text()); setError("");
  }
  const label = intent === "plan" ? "Selar plano" : intent === "enqueue" ? "Reservar e enfileirar" : "Solicitar cancelamento";
  return <form action={action} className="ops-form"><input type="hidden" name="org" value={org} /><input type="hidden" name="project" value={project} /><input type="hidden" name="intent" value={intent} /><input type="hidden" name="id" value={id ?? ""} /><input type="hidden" name="operation" value={operation} />
    {intent === "plan" && <><label className="ops-form__field">Arquivo de plano JSON<input type="file" disabled={!operation} accept="application/json,.json" onChange={event => void upload(event.target.files?.[0])} /></label><label className="ops-form__field">Runner e manifest JSON<textarea name="payload" disabled={!operation} rows={10} required value={payload} onChange={event => { setPayload(event.target.value); setError(""); }} /></label><p>Formato: objeto com runner_id e manifest. Selar não reserva orçamento nem executa código.</p></>}
    {intent === "enqueue" && <p>Esta ação reserva o teto declarado na organização e no projeto. Antes do lease, cancelar libera a reserva sem iniciar código.</p>}
    {state.error && <p role="alert">{state.error}</p>}{error && <p role="alert">{error}</p>}<Submit ready={!!operation && !error && (intent !== "plan" || !!payload)} label={label} /></form>;
}
