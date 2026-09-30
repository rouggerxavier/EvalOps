import type { QualityGateMetric, QualityGateSettings, QualityGateState } from "./types";

export const GATE_STATES: Record<QualityGateState, { label: string; variant: "ok" | "warn" | "err" }> = {
  pass: { label: "Aprovado", variant: "ok" },
  review: { label: "Revisão necessária", variant: "warn" },
  fail: { label: "Reprovado", variant: "err" },
};

export const GATE_METRICS: Record<QualityGateMetric, string> = {
  configuration: "Configuração", quality: "Qualidade", ungrounded: "Alucinação",
  avg_cost: "Custo médio", p95: "p95", critical: "Regras críticas",
};

export const GATE_REASONS: Record<string, string> = {
  not_configured: "Salve os limites do projeto em Settings para ativar o gate.",
  missing_evidence: "Sem evidência suficiente nesta janela.",
  incomplete_evidence: "Parte dos traces ainda não tem evidência completa.",
  threshold_exceeded: "O limite configurado foi violado.",
  within_threshold: "Dentro do limite configurado.",
  not_applicable: "Não se aplica nesta janela ou a exigência está desativada.",
};

/** UI percentages become API rates. Missing/invalid fields never become zero. */
export function parseQualityGateForm(form: FormData): QualityGateSettings | null {
  const number = (name: string) => {
    const raw = form.get(name);
    return typeof raw === "string" && raw.trim() !== "" ? Number(raw) : NaN;
  };
  const score = number("min_score_percent");
  const rate = number("max_ungrounded_percent");
  const cost = number("max_avg_cost_usd");
  const p95 = number("max_p95_ms");
  if (![score, rate, cost, p95].every(Number.isFinite) || score < 0 || score > 100 || rate < 0 || rate > 100 || cost < 0 || !Number.isInteger(p95) || p95 < 0 || p95 > 86400000) return null;
  return { min_score: score / 100, max_ungrounded_rate: rate / 100, max_avg_cost_usd: cost, max_p95_ms: p95, require_zero_critical: form.get("require_zero_critical") === "on" };
}
