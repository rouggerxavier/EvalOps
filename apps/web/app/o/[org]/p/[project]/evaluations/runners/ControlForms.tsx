"use client";
import { useEffect, useState } from "react";
import { useFormState, useFormStatus } from "react-dom";
import { controlRunner } from "./actions";
function Submit({ ready, label, intent }: { ready: boolean; label: string; intent?: string }) {
  const { pending } = useFormStatus();
  return <button className="btn btn--primary" disabled={!ready || pending} name={intent ? "intent" : undefined} value={intent}>{pending ? "Salvando…" : label}</button>;
}
function Fields({ org, project, operation }: { org: string; project: string; operation: string }) {
  return <><input type="hidden" name="org" value={org} /><input type="hidden" name="project" value={project} /><input type="hidden" name="operation" value={operation} /></>;
}
export function PolicyForm({ org, project, version, policy, organization = false }: { org: string; project: string; version: number; policy: unknown; organization?: boolean }) {
  const [state, action] = useFormState(controlRunner, {});
  const [operation, setOperation] = useState("");
  useEffect(() => setOperation(crypto.randomUUID()), [version]);
  return <form action={action} className="ops-form"><Fields org={org} project={project} operation={operation} /><input type="hidden" name="intent" value={organization ? "organization-budget" : "policy"} /><input type="hidden" name="revision" value={version} />
    <p>Revisão {version}. Alterações criam nova versão; revisão antiga recebe conflito.</p><label className="ops-form__field">{organization ? "Budget da organização JSON" : "Política de execução JSON"}<textarea name="policy" rows={12} defaultValue={JSON.stringify(policy, null, 2)} required /></label>
    {state.error && <p role="alert">{state.error}</p>}{state.message && <p role="status">{state.message}</p>}<Submit ready={!!operation} label={organization ? "Salvar budget da organização" : "Salvar versão da política"} /></form>;
}
export function RegisterForm({ org, project }: { org: string; project: string }) {
  const [state, action] = useFormState(controlRunner, {});
  const [operation, setOperation] = useState("");
  useEffect(() => setOperation(crypto.randomUUID()), []);
  useEffect(() => { if (state.message && !state.error) setOperation(crypto.randomUUID()); }, [state]);
  return <form action={action} className="ops-form"><Fields org={org} project={project} operation={operation} /><input type="hidden" name="intent" value="register" />
    <label className="ops-form__field">Nome do runner<input name="name" required maxLength={255} /></label><label className="ops-form__field">Ambientes permitidos JSON<input name="environments" defaultValue={'["dev"]'} required /></label><label className="ops-form__field">Adapters e versões JSON<textarea name="adapters" rows={3} defaultValue={'[{"id":"external-harness","version":"1"}]'} required /></label>
    <p>Isolamento é administrado pelo consumidor. Registro não comprova contenção de código hostil.</p>{state.error && <p role="alert">{state.error}</p>}{state.message && <p role="status">{state.message}</p>}<Submit ready={!!operation} label="Registrar runner" /></form>;
}
export function RunnerControls({ org, project, id, expires }: { org: string; project: string; id: string; expires: string }) {
  const [state, action] = useFormState(controlRunner, {});
  const [disabled, disable] = useFormState(controlRunner, {});
  const [operation, setOperation] = useState("");
  const [show, setShow] = useState(false);
  useEffect(() => setOperation(crypto.randomUUID()), []);
  return <><form action={action} className="ops-form"><Fields org={org} project={project} operation={operation} /><input type="hidden" name="runner_id" value={id} /><input type="hidden" name="credential_id" value={state.credential_id ?? ""} />
    <label className="ops-form__field">Expiração da credencial (ISO com timezone)<input name="expires_at" defaultValue={expires} required /></label>
    {state.key && <><label className="ops-form__field">Chave exclusiva do runner<input type={show ? "text" : "password"} readOnly value={state.key} autoComplete="off" /></label><label><input type="checkbox" checked={show} onChange={event => setShow(event.target.checked)} /> Mostrar chave</label><p>Credencial: <code style={{ overflowWrap: "anywhere" }}>{state.credential_id}</code></p></>}
    {state.error && <p role="alert">{state.error}</p>}{state.message && <p role="status">{state.message}</p>}<Submit ready={!!operation && !state.key} label="Criar credencial de runner" intent="credential" />{state.credential_id && <Submit ready={!!operation} label="Revogar credencial exibida" intent="revoke" />}</form>
    <form action={disable} className="ops-form"><Fields org={org} project={project} operation={`${operation}`} /><input type="hidden" name="runner_id" value={id} /><input type="hidden" name="intent" value="disable" />{disabled.error && <p role="alert">{disabled.error}</p>}<Submit ready={!!operation} label="Desabilitar runner" /></form></>;
}
