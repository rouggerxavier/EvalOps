import Link from "next/link";
import { Badge } from "./ui/Badge";
import { Card } from "./ui/Card";
import { formatCost, formatLatency } from "@/lib/format";
import { GATE_METRICS, GATE_REASONS, GATE_STATES } from "@/lib/quality-gate";
import type { QualityGateStatus } from "@/lib/types";

const percent = (value: number) => `${new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 }).format(value * 100)}%`;

export function QualityGateCard({ gate, settingsHref }: { gate: QualityGateStatus | null; settingsHref: string }) {
  if (!gate) return (
    <Card title="Controle de qualidade · Quality Gate" action={<Link className="btn btn--sm" href={settingsHref}>Configurar limites</Link>}>
      <p role="status">Não foi possível carregar o Quality Gate. Atualize a página para tentar novamente.</p>
    </Card>
  );
  const state = GATE_STATES[gate.status];
  return (
    <Card
      title="Controle de qualidade · Quality Gate"
      subtitle={`${gate.metrics.trace_count} traces · janela ${gate.window} · ambiente ${gate.environment ?? "todos"}`}
      action={<><Badge variant={state.variant}>{state.label}</Badge><Link className="btn btn--sm" href={settingsHref}>Configurar limites</Link></>}
    >
      <p className="quality-gate__intro">Resultado do gate: <strong>{state.label}</strong>. Limites do projeto aplicados às evidências de avaliações e operação.</p>
      <div className="quality-gate__metrics">
        {gate.reasons.filter((reason) => reason.metric !== "configuration").map((reason) => {
          const value = reason.observed === null ? "Sem evidência" : reason.metric === "avg_cost" ? formatCost(reason.observed) : reason.metric === "p95" ? formatLatency(reason.observed) : reason.metric === "critical" ? `${reason.observed} violações` : percent(reason.observed);
          const limit = reason.threshold === null ? "" : reason.metric === "avg_cost" ? formatCost(reason.threshold) : reason.metric === "p95" ? formatLatency(reason.threshold) : reason.metric === "critical" ? "zero violações" : percent(reason.threshold);
          const inactive = reason.code === "not_applicable";
          return (
            <div className="quality-gate__metric" key={reason.metric}>
              <h4>{GATE_METRICS[reason.metric]}</h4>
              <strong>{inactive ? reason.metric === "critical" ? "Exigência desativada" : "Não se aplica" : value}</strong>
              <span>{!inactive && `Limite ${reason.metric === "quality" ? "mínimo" : "máximo"}: ${limit}`}</span>
              <Badge variant={inactive ? "default" : GATE_STATES[reason.status].variant}>{inactive ? "Não exigido" : GATE_STATES[reason.status].label}</Badge>
              <p>{reason.code === "not_configured" ? "Limites sugeridos; salve para ativar." : GATE_REASONS[reason.code] ?? "Confira as evidências do projeto."}</p>
              {!inactive && <span>{reason.sample_count} traces com evidência</span>}
            </div>
          );
        })}
      </div>
      {!gate.config.configured && <p role="status">{GATE_REASONS.not_configured}</p>}
      <p className="quality-gate__note">Alucinação é um indicador de afirmações sem suporte, medido apenas em traces RAG. Custos em USD por trace, conforme registrados. Regras críticas usam condições de reprovação ligadas a avaliadores das rubricas.</p>
    </Card>
  );
}
