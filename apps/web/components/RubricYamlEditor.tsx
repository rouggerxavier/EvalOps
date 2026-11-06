"use client";

import { useState } from "react";

import { judgeStatusText, setJudgeModel } from "@/lib/cli-judge.mjs";
import type { CliJudgeOption } from "@/lib/types";

type Props = {
  label: string;
  defaultValue: string;
  judges: CliJudgeOption[];
};

export function RubricYamlEditor({ label, defaultValue, judges }: Props) {
  const [yaml, setYaml] = useState(defaultValue);
  const [judge, setJudge] = useState("");

  const selectedHint = judge
    ? "Modo local: roda a CLI logada nesta máquina, sem ferramentas, uma avaliação por vez. Consome a cota do seu plano e o custo fica desconhecido. Login expirado só aparece ao avaliar, como “não mediu”."
    : "Juízes por CLI só funcionam neste computador, nunca em produção.";

  return (
    <>
      {judges.length > 0 && (
        <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 13 }}>
          <span style={{ color: "var(--text-muted)" }}>Juiz local (opcional)</span>
          <select
            value={judge}
            onChange={(event) => {
              setJudge(event.target.value);
              if (event.target.value) setYaml((current) => setJudgeModel(current, event.target.value));
            }}
            style={{
              background: "var(--bg-2)",
              border: "1px solid var(--border)",
              borderRadius: 6,
              padding: "6px 10px",
              color: "var(--text)",
              fontSize: 13,
              width: "100%",
            }}
          >
            <option value="">Manter o que está no YAML</option>
            {judges.map((option) => (
              <option key={option.provider} value={option.model} disabled={option.status !== "available"}>
                {option.model} — {judgeStatusText(option.status)}
                {option.version ? ` (${option.version})` : ""}
              </option>
            ))}
          </select>
          <span style={{ fontSize: 12, color: judge ? "var(--warning)" : "var(--text-faint)", lineHeight: 1.5 }}>
            {selectedHint}
          </span>
        </label>
      )}
      <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 13 }}>
        <span style={{ color: "var(--text-muted)" }}>{label}</span>
        <textarea
          name="yaml_source"
          required
          rows={12}
          value={yaml}
          onChange={(event) => setYaml(event.target.value)}
          style={{
            background: "var(--bg-2)",
            border: "1px solid var(--border)",
            borderRadius: 6,
            padding: "6px 10px",
            color: "var(--text)",
            width: "100%",
            fontFamily: "var(--font-mono)",
            fontSize: 12,
            resize: "vertical",
          }}
        />
      </label>
    </>
  );
}
