"use client";
import { useEffect, useState } from "react";
import { useFormState, useFormStatus } from "react-dom";
import { importExecution } from "./actions";
function Submit({ ready }: { ready: boolean }) {
  const { pending } = useFormStatus();
  return <button className="btn btn--primary" disabled={!ready || pending}>{pending ? "Importando…" : "Importar evidência de harness"}</button>;
}
export function ImportForm({ org, project }: { org: string; project: string }) {
  const [state, action] = useFormState(importExecution, {});
  const [operation, setOperation] = useState("");
  const [capture, setCapture] = useState("");
  const [error, setError] = useState("");
  useEffect(() => setOperation(crypto.randomUUID()), []);
  let valid = false;
  try { const data = JSON.parse(capture); valid = !!data?.manifest && !!data?.result && new TextEncoder().encode(capture).length <= 10 * 1024 * 1024; } catch { valid = false; }
  async function upload(file?: File) {
    if (!file) return;
    if (file.size > 10 * 1024 * 1024) { setError("Arquivo excede 10 MiB."); return; }
    setCapture(await file.text()); setError("");
  }
  return <form action={action} className="ops-form">
    <input type="hidden" name="org" value={org} /><input type="hidden" name="project" value={project} /><input type="hidden" name="operation" value={operation} />
    <label className="ops-form__field">Arquivo de captura JSON<input type="file" accept="application/json,.json" onChange={event => void upload(event.target.files?.[0])} /></label>
    <label className="ops-form__field">Manifest e resultado JSON<textarea name="capture" rows={12} value={capture} onChange={event => { setCapture(event.target.value); setError(""); }} /></label>
    <p>Importe manifest e result do harness, vinculados ao snapshot e às predições já importadas. Limite 10 MiB. Credenciais e segredos não pertencem ao arquivo.</p>
    {!valid && <p role="status">Informe um objeto JSON com manifest e result.</p>}{error && <p role="alert">{error}</p>}{state.error && <p role="alert">{state.error}</p>}<Submit ready={valid && !!operation && !error} />
  </form>;
}
