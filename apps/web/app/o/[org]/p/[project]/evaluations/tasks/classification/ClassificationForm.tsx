"use client";
import { useEffect, useState } from "react";
import { useFormState, useFormStatus } from "react-dom";
import { importClassification } from "../actions";
function Submit({ ready }: { ready: boolean }) {
  const { pending } = useFormStatus();
  return <button className="btn btn--primary" disabled={!ready || pending}>{pending ? "Avaliando…" : "Importar classificação e avaliar"}</button>;
}
export function ClassificationForm({ org, project, environment, snapshots, models }: { org: string; project: string; environment: string; snapshots: { id: string; label: string }[]; models: { id: string; name: string; version_ref: string }[] }) {
  const [state, action] = useFormState(importClassification, {});
  const [operation, setOperation] = useState("");
  const [content, setContent] = useState('{"items":[],"rows":[]}');
  const [snapshot, setSnapshot] = useState("");
  const [model, setModel] = useState("");
  const [error, setError] = useState("");
  useEffect(() => setOperation(crypto.randomUUID()), []);
  let preview: { sample_id: string; expected_output?: { label?: string }; prediction?: { label?: string } }[] = [];
  let valid = false;
  try {
    const data = JSON.parse(content);
    valid = Array.isArray(data.items) && Array.isArray(data.rows) && data.rows.length > 0 && data.rows.length <= 10000 && new TextEncoder().encode(content).length <= 10 * 1024 * 1024;
    if (valid) preview = data.rows.slice(0, 10).map((row: { sample_id: string; prediction?: { label?: string } }) => {
      if (!row || typeof row.sample_id !== "string" || row.prediction?.label != null && typeof row.prediction.label !== "string") throw new Error("invalid_row");
      const reference = data.items.find((item: { sample_id: string }) => item && item.sample_id === row.sample_id)?.expected_output;
      if (reference?.label != null && typeof reference.label !== "string") throw new Error("invalid_reference");
      return { sample_id: row.sample_id, prediction: row.prediction, expected_output: reference };
    });
  } catch { valid = false; }
  async function upload(file?: File) {
    if (!file) return;
    if (file.size > 10 * 1024 * 1024) { setError("Arquivo excede 10 MiB."); return; }
    setContent(await file.text()); setError("");
  }
  return <form action={action} className="ops-form">
    <input type="hidden" name="org" value={org} /><input type="hidden" name="project" value={project} /><input type="hidden" name="operation" value={operation} /><input type="hidden" name="environment" value={environment} />
    <label className="ops-form__field">Snapshot de classificação<select name="snapshot_id" value={snapshot} onChange={event => setSnapshot(event.target.value)}><option value="">Criar dataset e snapshot</option>{snapshots.map(row => <option key={row.id} value={row.id}>{row.label}</option>)}</select></label>
    <label className="ops-form__field">Modelo de classificação<select name="model_version_id" value={model} onChange={event => setModel(event.target.value)}><option value="">Declarar nova versão</option>{models.map(row => <option key={row.id} value={row.id}>{row.name}@{row.version_ref}</option>)}</select></label>
    <label className="ops-form__field">Dataset (slug)<input name="slug" required={!snapshot} disabled={!!snapshot} pattern="[a-z0-9-]{2,}" /></label>
    <label className="ops-form__field">Classes ordenadas JSON<input name="labels" required={!snapshot} disabled={!!snapshot} defaultValue={'["no","yes"]'} /></label>
    <label className="ops-form__field">Classe positiva (obrigatória no binário)<input name="positive_label" disabled={!!snapshot} defaultValue="yes" /></label>
    <label className="ops-form__field">Segmentos JSON<input name="segments" disabled={!!snapshot} defaultValue="[]" /></label>
    <label className="ops-form__field">Modelo<input name="model" required={!model} disabled={!!model} /></label><label className="ops-form__field">Versão declarada<input name="version" required={!model} disabled={!!model} /></label>
    <p>Ambiente {environment}. A ordem de class_order deve coincidir com as classes. Probabilidades são opcionais; ausência não vira zero.</p>
    <label className="ops-form__field">Importar arquivo de classificação JSON<input type="file" accept="application/json,.json" onChange={event => void upload(event.target.files?.[0])} /></label>
    <label className="ops-form__field">Dados de classificação JSON<textarea name="rows" rows={10} value={content} onChange={event => { setContent(event.target.value); setError(""); }} /></label>
    <details><summary>Formato da importação</summary><pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{'{"items":[{"sample_id":"s1","input":{},"expected_output":{"label":"yes"}}],"rows":[{"sample_id":"s1","prediction":{"label":"yes","class_order":["no","yes"],"probabilities":[0.1,0.9]}}]}'}</pre><p>Use expected_output: null para referência ausente. Para snapshot existente, envie items: [] e mantenha os IDs nas predições.</p></details>
    <h3>Prévia das primeiras 10 predições</h3><div className="table-wrap"><table className="t"><thead><tr><th>Amostra</th><th>Referência</th><th>Predição</th></tr></thead><tbody>{preview.map((row, i) => <tr key={i}><td>{row.sample_id}</td><td>{row.expected_output?.label ?? "Ausente"}</td><td>{row.prediction?.label ?? "Ausente"}</td></tr>)}</tbody></table></div>
    {!valid && <p role="status">Informe JSON válido com items e rows. Limite: 10 mil linhas e 10 MiB.</p>}{error && <p role="alert">{error}</p>}{state.error && <p role="alert">{state.error}</p>}<Submit ready={valid && !!operation && !error} />
  </form>;
}
