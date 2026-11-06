import Link from "next/link";
import type { CSSProperties } from "react";
import {
  ArrowRight,
  BookOpen,
} from "lucide-react";

import { EvalOpsFeatureStepper } from "@/components/EvalOpsFeatureStepper";
import { FinalLandingCta } from "@/components/FinalLandingCta";
import { HowItWorksPipeline } from "@/components/HowItWorksPipeline";
import { IntegrationLogoLoop } from "@/components/IntegrationLogoLoop";
import LightPillar from "@/components/LightPillar";
import { MarketingFooter } from "@/components/MarketingFooter";
import { MarketingNav } from "@/components/MarketingNav";
import { SDKShowcase } from "@/components/SDKShowcase";

const heroMockMetrics = [
  { label: "Traces", value: "14,287", trend: "+12.4% vs 24h", tone: "good", spark: "M4,38 L20,34 L36,36 L52,24 L68,28 L84,18 L100,22 L116,12" },
  { label: "p95 Latência", value: "1.14s", trend: "+38ms", tone: "warn", spark: "M4,30 L20,26 L36,34 L52,20 L68,16 L84,24 L100,18 L116,8" },
  { label: "Custo", value: "$13.42", trend: "+8.1%", tone: "good", spark: "M4,36 L20,30 L36,34 L52,20 L68,28 L84,16 L100,22 L116,10" },
  { label: "Erro", value: "1.8%", trend: "-0.4pp", tone: "good", spark: "M4,34 L18,18 L32,32 L46,8 L60,24 L74,38 L88,30 L102,18 L116,28" },
];

const heroMockModels = [
  { model: "gpt-4o-mini", provider: "openai", calls: "8.420", cost: "$4.2380", share: "41%" },
  { model: "gpt-4.1", provider: "openai", calls: "1.206", cost: "$6.8104", share: "32%" },
  { model: "claude-haiku-4.5", provider: "anthropic", calls: "2.310", cost: "$1.4720", share: "14%" },
  { model: "llama-3.3-70b", provider: "groq", calls: "1.840", cost: "$0.5210", share: "8%" },
  { model: "2.5-flash", provider: "gemini", calls: "920", cost: "$0.4080", share: "5%" },
];

const heroMockIssues = [
  { trace: "support.refund.flow", status: "schema_mismatch", score: "0.42" },
  { trace: "billing.plan.change", status: "timeout", score: "0.58" },
  { trace: "rag.answer.compose", status: "low_confidence", score: "0.61" },
];

export default function HomePage() {
  return (
    <div className="mk-shell">
      <div className="bg-stage">
        <div className="bg-pillar" aria-hidden="true">
          <LightPillar
            topColor="#5aa3ff"
            bottomColor="#1a2a7a"
            intensity={1.08}
            rotationSpeed={0.2}
            glowAmount={0.008}
            pillarWidth={3.0}
            pillarHeight={0.34}
            noiseIntensity={0.52}
            pillarRotation={130}
            interactive={false}
            mixBlendMode="screen"
            quality="medium"
          />
        </div>
        <div className="bg-grid" />
      </div>

      <MarketingNav variant="landing" />

      <main className="mk-wrap">
        <section className="hero mk-container">
          <span className="hero__pill">
            <span>Controle de qualidade para agentes de IA</span>
            <span>LLMOps · tracing, avaliação e experimentos</span>
            <span className="arrow">&rsaquo;</span>
          </span>
          <h1>
            Controle de qualidade
            <br />
            para <em>agentes de IA.</em>
          </h1>
          <p className="hero__lede">
            Saiba se seu agente atende aos requisitos da empresa. Defina limites de qualidade, respostas sem suporte, custo e latência com um Quality Gate por projeto.
            Tracing, rubricas e experimentos LLMOps fornecem as evidências para decidir.
          </p>
          <div className="hero__cta">
            <Link className="mk-btn mk-btn--primary mk-btn--lg" href="/register">
              Comece a medir qualidade
              <ArrowRight />
            </Link>
            <Link className="mk-btn mk-btn--secondary mk-btn--lg" href="/docs">
              <BookOpen />
              Ler a documentação
            </Link>
          </div>
          <div className="hero__meta">
            <span><code>pip install -e packages/sdk-python</code></span>
            <span className="dot" />
            <span>SDK Python - compatível com OpenTelemetry - pronto para self-host</span>
          </div>

          <div className="hero__preview">
            <div className="dash-mock">
              <aside className="dash-mock__sidebar">
                <div className="dash-mock__brand">
                  <img src="/brand/mark-evalops.svg" style={{ width: 18, height: 18 }} alt="" />
                  <span>EvalOps</span>
                  <span className="dash-mock__version">v1.0</span>
                </div>
                <div className="dash-mock__workspace">
                  <span>ACME - PROD</span>
                  <strong>aurora-support</strong>
                </div>
                <div className="dash-mock__nav">
                  <span className="dash-mock__nav-label">Projeto</span>
                  {["Visão geral", "Traces", "Evaluations", "Experiments"].map((item, index) => (
                    <div key={item} className={`item${index === 0 ? " active" : ""}`}>
                      <span className="dot" />
                      {item}
                      {item === "Traces" ? <small>1.2k</small> : null}
                    </div>
                  ))}
                  <span className="dash-mock__nav-label">Recursos</span>
                  {["Prompts", "Rubrics", "Datasets"].map((item) => (
                    <div key={item} className="item">
                      <span className="dot" />
                      {item}
                    </div>
                  ))}
                  <span className="dash-mock__nav-label">Operação</span>
                  {["API Keys", "Exports"].map((item) => (
                    <div key={item} className="item">
                      <span className="dot" />
                      {item}
                    </div>
                  ))}
                </div>
              </aside>
              <div className="dash-mock__main">
                <div className="dash-mock__bar">
                  <div className="dash-mock__crumbs">
                    <span>acme</span>
                    <span>aurora-support</span>
                    <strong>Visão geral</strong>
                  </div>
                  <div className="dash-mock__search">Buscar traces, prompts, rubrics...</div>
                  <span className="dash-mock__chip live">&bull; env: prod</span>
                  <span className="dash-mock__avatar">RX</span>
                </div>
                <div className="dash-mock__header">
                  <div>
                    <h3>Aurora Support AI</h3>
                    <p>Resumo de operação · janela: últimas 24h · env: prod</p>
                  </div>
                  <div className="dash-mock__actions">
                    <span className="dash-mock__chip">Últimas 24h</span>
                    <span className="dash-mock__chip">Atualizar</span>
                    <span className="dash-mock__run">Rodar evaluation</span>
                  </div>
                </div>
                <div className="dash-mock__kpis">
                  {heroMockMetrics.map((metric) => (
                    <div className="dash-mock__kpi" key={metric.label}>
                      <div className="l">{metric.label}</div>
                      <div className="v">{metric.value}</div>
                      <div className={`d ${metric.tone}`}>{metric.trend}</div>
                      <svg viewBox="0 0 120 44" preserveAspectRatio="none" aria-hidden="true">
                        <path d={metric.spark} />
                      </svg>
                    </div>
                  ))}
                </div>
                <div className="dash-mock__content">
                  <div className="dash-mock__chart">
                    <div className="head">
                      <div>
                        <span className="t">Custo & volume por dia</span>
                        <span>USD · últimos 14 dias</span>
                      </div>
                      <span className="dash-mock__metric-pill">cost</span>
                    </div>
                    <svg viewBox="0 0 660 270" preserveAspectRatio="none" aria-hidden="true">
                      <defs>
                        <linearGradient id="hero-cost-area" x1="0" x2="0" y1="0" y2="1">
                          <stop offset="0%" stopColor="#4f8cff" stopOpacity="0.5" />
                          <stop offset="100%" stopColor="#4f8cff" stopOpacity="0.02" />
                        </linearGradient>
                      </defs>
                      <line x1="0" y1="72" x2="660" y2="72" />
                      <line x1="0" y1="136" x2="660" y2="136" />
                      <line x1="0" y1="200" x2="660" y2="200" />
                      <path
                        className="area"
                        d="M0,194 L58,176 L116,182 L174,160 L232,148 L290,170 L348,126 L406,130 L464,102 L522,118 L580,88 L660,58 L660,270 L0,270 Z"
                      />
                      <path
                        className="line"
                        d="M0,194 L58,176 L116,182 L174,160 L232,148 L290,170 L348,126 L406,130 L464,102 L522,118 L580,88 L660,58"
                      />
                      {[0, 116, 232, 348, 464, 580].map((x, index) => (
                        <text key={x} x={x} y="252">{["/05", "06/05", "08/05", "10/05", "12/05", "14/05"][index]}</text>
                      ))}
                    </svg>
                  </div>
                  <div className="dash-mock__models">
                    <div className="head">
                      <span className="t">Custo por modelo</span>
                      <span>Ver detalhes</span>
                    </div>
                    <div className="dash-mock__table-head">
                      <span>Modelo</span>
                      <span>Calls</span>
                      <span>Custo</span>
                      <span>Share</span>
                    </div>
                    {heroMockModels.map((row) => (
                      <div className="dash-mock__model-row" key={row.model}>
                        <div>
                          <strong>{row.model}</strong>
                          <small>{row.provider}</small>
                        </div>
                        <span>{row.calls}</span>
                        <span>{row.cost}</span>
                        <span className="dash-mock__share" style={{ "--share": row.share } as CSSProperties}>
                          <i />
                          {row.share}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="dash-mock__issues">
                  <div className="head">
                    <span className="t">Últimos traces com problema</span>
                    <span>Ver todos os traces</span>
                  </div>
                  <div className="dash-mock__issue-list">
                    {heroMockIssues.map((issue) => (
                      <div className="dash-mock__issue" key={issue.trace}>
                        <span>{issue.trace}</span>
                        <small>{issue.status}</small>
                        <strong>{issue.score}</strong>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>

          <IntegrationLogoLoop />
        </section>

        <section className="mk-section" id="product">
          <div className="mk-container">
            <span className="mk-eyebrow">A plataforma</span>
            <h2>Tudo para publicar apps LLM sem degradação silenciosa.</h2>
            <p className="lede">
              Um fluxo guiado para instrumentar, avaliar, comparar e liberar com segurança sem sobrecarregar a equipe
              com dezenas de cards ao mesmo tempo.
            </p>
            <EvalOpsFeatureStepper />
          </div>
        </section>

        <section className="mk-section" id="sdk">
          <div className="mk-container">
            <SDKShowcase />
          </div>
        </section>

        <section className="mk-section" id="how">
          <div className="mk-container">
            <span className="mk-eyebrow">Como funciona</span>
            <h2>Do tráfego de produção ao quality gate do projeto.</h2>
            <HowItWorksPipeline />
          </div>
        </section>

        <section className="mk-section">
          <div className="mk-container">
            <FinalLandingCta />
          </div>
        </section>

        <MarketingFooter />
      </main>
    </div>
  );
}


