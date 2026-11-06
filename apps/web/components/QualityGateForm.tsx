import { saveQualityGateAction } from "@/lib/actions";
import type { QualityGateConfig } from "@/lib/types";
import { Card } from "./ui/Card";

export function QualityGateForm({ config, org, project }: { config: QualityGateConfig | null; org: string; project: string }) {
  return (
    <div id="quality-gate">
      <Card title="Quality Gate · limites de qualidade" subtitle="Controle de qualidade para agentes de IA">
        {!config ? <p role="status">Não foi possível carregar os limites. Atualize a página para tentar novamente.</p> : (
          <>
            <p className="quality-gate__intro">Defina quando o agente atende aos requisitos da empresa. {config.configured ? "Limites salvos para este projeto." : "Os valores abaixo são sugestões. Salve para ativar o gate."}</p>
            <form action={saveQualityGateAction} className="quality-gate__form">
              <input type="hidden" name="org" value={org} />
              <input type="hidden" name="project" value={project} />
              <label>Score mínimo de qualidade (%)<input className="filter-input" type="number" name="min_score_percent" min="0" max="100" step="any" required defaultValue={config.min_score * 100} /></label>
              <label>Taxa máxima de alucinação / sem suporte (%)<input className="filter-input" type="number" name="max_ungrounded_percent" min="0" max="100" step="any" required defaultValue={config.max_ungrounded_rate * 100} /></label>
              <label>Custo médio máximo por trace (USD)<input className="filter-input" type="number" name="max_avg_cost_usd" min="0" step="any" required defaultValue={config.max_avg_cost_usd} /></label>
              <label>Latência p95 máxima (ms)<input className="filter-input" type="number" name="max_p95_ms" min="0" max="86400000" step="1" required defaultValue={config.max_p95_ms} /></label>
              <label className="quality-gate__checkbox"><input type="checkbox" name="require_zero_critical" defaultChecked={config.require_zero_critical} />Exigir zero violações críticas</label>
              <p className="quality-gate__note">O resultado usa a janela e o ambiente selecionados na visão geral. Falta de avaliações, grounding ou regras críticas verificadas pede revisão. Este gate informa a decisão; não bloqueia chamadas ou deployments.</p>
              <button type="submit" className="btn btn--sm btn--primary">Salvar Quality Gate</button>
            </form>
          </>
        )}
      </Card>
    </div>
  );
}
