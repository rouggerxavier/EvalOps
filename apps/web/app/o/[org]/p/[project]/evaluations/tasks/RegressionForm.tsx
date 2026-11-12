"use client";

import { useEffect, useState } from "react";
import { useFormState, useFormStatus } from "react-dom";
import { importRegression } from "./actions";

type Row = { sample_id: string; expected: string; predicted: string; input: string };
function Submit({ disabled }: { disabled: boolean }) {
  const { pending } = useFormStatus();
  return <button className="btn btn--primary" disabled={disabled || pending}>{pending ? "Avaliando…" : "Importar e avaliar"}</button>;
}

export function RegressionForm({ org, project, environment, snapshots, models }: { org: string; project: string; environment: string; snapshots: { id: string; label: string }[]; models: { id: string; name: string; version_ref: string }[] }) {
  const [state, action] = useFormState(importRegression, {});
  const [operation, setOperation] = useState("");
  const [rows, setRows] = useState<Row[]>([{ sample_id: "", expected: "", predicted: "", input: "{}" }]);
  const [snapshotId, setSnapshotId] = useState("");
  const [modelId, setModelId] = useState("");
  const [fileError, setFileError] = useState("");
  useEffect(() => setOperation(crypto.randomUUID()), []);
  let payload = "";
  let invalid = "";
  try {
    const ids = new Set<string>();
    const items = rows.map(row => {
      if (!row.sample_id.trim() || ids.has(row.sample_id)) throw new Error("Informe IDs únicos para todas as amostras.");
      ids.add(row.sample_id);
      const input: unknown = JSON.parse(row.input);
      if (!input || Array.isArray(input) || typeof input !== "object") throw new Error("Input deve ser um objeto JSON.");
      const value = row.expected.trim() === "" ? null : Number(row.expected);
      if (value !== null && !Number.isFinite(value)) throw new Error("Referência deve ser finita ou vazia.");
      return { sample_id: row.sample_id, input, expected_output: { value } };
    });
    const predictions = rows.filter(row => row.predicted.trim() !== "").map(row => {
      const value = Number(row.predicted);
      if (!Number.isFinite(value)) throw new Error("Predição deve ser finita ou vazia.");
      return { sample_id: row.sample_id, prediction: { value } };
    });
    payload = JSON.stringify({ items, rows: predictions });
    if (rows.length > 10000 || new TextEncoder().encode(payload).length > 10 * 1024 * 1024) throw new Error("Limite: 10 mil linhas e 10 MiB.");
  } catch (error) { invalid = error instanceof Error ? error.message : "Dados inválidos."; }
  function update(index: number, key: keyof Row, value: string) {
    setFileError("");
    setRows(current => current.map((row, i) => i === index ? { ...row, [key]: value } : row));
  }
  async function upload(file?: File) {
    setFileError("");
    if (!file) return;
    try {
      if (file.size > 10 * 1024 * 1024) throw new Error("Arquivo excede 10 MiB.");
      const data: unknown = JSON.parse(await file.text());
      if (!Array.isArray(data) || !data.length || data.length > 10000) throw new Error("Envie um array com 1 a 10 mil linhas.");
      const parsed: Row[] = data.map(row => {
        if (!row || typeof row.sample_id !== "string" || (row.expected !== null && typeof row.expected !== "number") || (row.predicted !== null && typeof row.predicted !== "number")) throw new Error("Cada linha exige sample_id, expected e predicted; números ausentes usam null.");
        if ((row.expected !== null && !Number.isFinite(row.expected)) || (row.predicted !== null && !Number.isFinite(row.predicted))) throw new Error("Números devem ser finitos.");
        return { sample_id: row.sample_id, expected: row.expected === null ? "" : String(row.expected), predicted: row.predicted === null ? "" : String(row.predicted), input: JSON.stringify(row.input ?? {}) };
      });
      setRows(parsed);
    } catch (error) { setFileError(error instanceof Error ? error.message : "Arquivo inválido."); }
  }
  return <form action={action} className="form-stack">
    <input type="hidden" name="org" value={org} /><input type="hidden" name="project" value={project} />
    <input type="hidden" name="environment" value={environment} /><input type="hidden" name="operation" value={operation} />
    <input type="hidden" name="rows" value={payload} />
    <label>Snapshot existente<select name="snapshot_id" value={snapshotId} onChange={event => setSnapshotId(event.target.value)}><option value="">Criar dataset e snapshot</option>{snapshots.map(row => <option key={row.id} value={row.id}>{row.label}</option>)}</select></label>
    {snapshotId && <p>O snapshot fornece as referências congeladas. Importe os mesmos IDs com novas predições.</p>}
    <label>Modelo existente<select name="model_version_id" value={modelId} onChange={event => setModelId(event.target.value)}><option value="">Declarar nova versão</option>{models.map(row => <option key={row.id} value={row.id}>{row.name}@{row.version_ref}</option>)}</select></label>
    <div className="filter-grid">
      <label>Dataset (slug)<input name="slug" required={!snapshotId} disabled={!!snapshotId} pattern="[a-z0-9-]{2,}" maxLength={255} /></label>
      <label>Alvo<input name="target" required={!snapshotId} disabled={!!snapshotId} /></label>
      <label>Unidade<input name="unit" required={!snapshotId} disabled={!!snapshotId} placeholder="BRL, kg, 1…" /></label>
      <label>Modelo<input name="model" required={!modelId} disabled={!!modelId} /></label>
      <label>Versão declarada<input name="version" required={!modelId} disabled={!!modelId} /></label>
    </div>
    <p>Ambiente: {environment}. Referências importadas permanecem em rascunho. Valores vazios reduzem a cobertura.</p>
    <label>Importar arquivo JSON<input type="file" accept="application/json,.json" onChange={event => void upload(event.target.files?.[0])} /></label>
    <p>Formato por linha: <code>{'{"sample_id":"s1","input":{},"expected":1,"predicted":1.2}'}</code>. Envie um array; use null para valor ausente.</p>
    {fileError && <p role="alert">{fileError}</p>}
    <div className="table-wrap"><table><caption>Amostras e predições ({rows.length}); prévia das primeiras 20 linhas</caption><thead><tr><th>ID da amostra</th><th>Referência</th><th>Predição</th><th>Input JSON</th><th>Ações</th></tr></thead><tbody>
      {rows.slice(0, 20).map((row, index) => <tr key={index}>
        <td><input aria-label={`ID da amostra ${index + 1}`} value={row.sample_id} onChange={event => update(index, "sample_id", event.target.value)} required /></td>
        <td><input aria-label={`Referência ${index + 1}`} type="number" step="any" value={row.expected} onChange={event => update(index, "expected", event.target.value)} /></td>
        <td><input aria-label={`Predição ${index + 1}`} type="number" step="any" value={row.predicted} onChange={event => update(index, "predicted", event.target.value)} /></td>
        <td><input aria-label={`Input JSON ${index + 1}`} value={row.input} onChange={event => update(index, "input", event.target.value)} /></td>
        <td><button type="button" className="btn" disabled={rows.length === 1} onClick={() => setRows(current => current.filter((_, i) => i !== index))}>Remover</button></td>
      </tr>)}
    </tbody></table></div>
    <button className="btn" type="button" disabled={rows.length >= 10000} onClick={() => setRows(current => [...current, { sample_id: "", expected: "", predicted: "", input: "{}" }])}>Adicionar amostra</button>
    {invalid && <p role="status">{invalid}</p>}{state.error && <p role="alert">{state.error}</p>}
    <Submit disabled={!!invalid || !!fileError || !operation} />
  </form>;
}
