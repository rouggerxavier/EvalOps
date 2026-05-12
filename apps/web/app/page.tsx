import Link from "next/link";
import {
  Activity,
  ArrowRight,
  BookOpen,
  DollarSign,
  Gauge,
  Github,
  GitCompare,
  ShieldCheck,
  ThumbsUp,
} from "lucide-react";

import LightPillar from "@/components/LightPillar";
import { MarketingFooter } from "@/components/MarketingFooter";
import { MarketingNav } from "@/components/MarketingNav";

const features = [
  {
    Icon: Activity,
    title: "Tracing estruturado para agentes",
    body: "Capture a árvore completa de execução: chamadas LLM, ferramentas, retrievals e fallbacks com tokens, custo e latência em cada span.",
    chip: "FR-20 / FR-25",
  },
  {
    Icon: Gauge,
    title: "Rubricas como código",
    body: "Declare qualidade em YAML. LLM-as-judge, regex, validação de schema, similaridade cosseno e exact match podem ser compostos e versionados.",
    chip: "FR-30 / FR-31 / FR-33",
  },
  {
    Icon: GitCompare,
    title: "Experimentos e regressão",
    body: "Rode um golden set contra variantes de prompt ou modelo. Compare pass rate, custo e latência antes de publicar.",
    chip: "FR-42 / FR-43 / FR-44",
  },
  {
    Icon: ThumbsUp,
    title: "Feedback que vira dado de treino",
    body: "Revisões humanas entram nos datasets. Exporte traces aprovados como JSONL para fine-tuning, few-shot ou análise offline.",
    chip: "FR-60 / FR-63 / FR-64",
  },
  {
    Icon: DollarSign,
    title: "Custo visível por padrão",
    body: "Cada span carrega custo em USD. Agrupe por modelo, projeto, ambiente ou usuário e encontre prompts caros antes que virem surpresa.",
    chip: "FR-50 / FR-53",
  },
  {
    Icon: ShieldCheck,
    title: "Schema pronto para privacidade",
    body: "Redação, retenção e auditoria fazem parte do modelo desde o início: chaves API com hash, ownership claro e hooks de compliance.",
    chip: "NFR-21 / NFR-30 / NFR-31",
  },
];

const steps = [
  {
    step: "ETAPA 01",
    title: "Instrumente",
    body: "Adicione o SDK ou envie traces por POST diretamente. Spans, ferramentas e eventos entram em um único grafo de execução.",
  },
  {
    step: "ETAPA 02",
    title: "Avalie",
    body: "Rode rubricas na ingestão ou manualmente. Cada trace recebe score, reasoning e status de aprovação.",
  },
  {
    step: "ETAPA 03",
    title: "Compare",
    body: "Rode experimentos entre prompts, modelos ou parâmetros e compare qualidade, custo e latência.",
  },
  {
    step: "ETAPA 04",
    title: "Melhore",
    body: "Promova a melhor variante e exporte exemplos de alta qualidade para fine-tuning ou suítes de regressão.",
  },
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
            <span>Observabilidade contínua para apps de IA em produção</span>
            <span>v0.7 - tracing, avaliação e experimentos</span>
            <span className="arrow">&rsaquo;</span>
          </span>
          <h1>
            Observabilidade e <em>avaliação</em>
            <br />
            para aplicações de IA.
          </h1>
          <p className="hero__lede">
            Trace cada chamada LLM. Avalie cada resposta com rubricas declarativas. Compare prompts e modelos
            em tráfego de produção antes que a qualidade desvie em silêncio.
          </p>
          <div className="hero__cta">
            <Link className="mk-btn mk-btn--primary mk-btn--lg" href="/register">
              Comece a rastrear grátis
              <ArrowRight />
            </Link>
            <Link className="mk-btn mk-btn--secondary mk-btn--lg" href="/docs">
              <BookOpen />
              Ler a documentação
            </Link>
          </div>
          <div className="hero__meta">
            <span><code>pip install evalops</code></span>
            <span className="dot" />
            <span>SDK Python - compatível com OpenTelemetry - pronto para self-host</span>
          </div>

          <div className="hero__preview">
            <div className="dash-mock">
              <aside className="dash-mock__sidebar">
                <div className="dash-mock__brand">
                  <img src="/brand/mark-evalops.svg" style={{ width: 18, height: 18 }} alt="" />
                  EvalOps
                </div>
                <div className="dash-mock__nav">
                  {["Visão geral", "Traces", "Avaliações", "Rubricas", "Experimentos", "Datasets", "Prompts", "Chaves API"].map((item, index) => (
                    <div key={item} className={`item${index === 0 ? " active" : ""}`}>
                      <span className="dot" />
                      {item}
                    </div>
                  ))}
                </div>
              </aside>
              <div className="dash-mock__main">
                <div className="dash-mock__bar">
                  <span className="dash-mock__chip">DocOps Agent</span>
                  <span className="dash-mock__chip live">&bull; prod</span>
                  <span className="dash-mock__chip">Últimos 7d</span>
                  <span style={{ flex: 1 }} />
                  <span className="dash-mock__chip" style={{ fontFamily: "var(--font-mono)" }}>
                    trace_9f8d2a7c
                  </span>
                </div>
                <div className="dash-mock__kpis">
                  <div className="dash-mock__kpi"><div className="l">Traces</div><div className="v">128,547</div><div className="d">+18.6%</div></div>
                  <div className="dash-mock__kpi"><div className="l">Score médio</div><div className="v">0.86</div><div className="d">+6.3%</div></div>
                  <div className="dash-mock__kpi"><div className="l">Latência P95</div><div className="v">2.48s</div><div className="d">-9.7%</div></div>
                  <div className="dash-mock__kpi"><div className="l">Custo</div><div className="v">$1,842</div><div className="d">-14.2%</div></div>
                </div>
                <div className="dash-mock__chart">
                  <div className="head">
                    <span className="t">Traces ao longo do tempo</span>
                    <span>Diário v</span>
                  </div>
                  <svg viewBox="0 0 600 160" preserveAspectRatio="none">
                    <defs>
                      <linearGradient id="ar" x1="0" x2="0" y1="0" y2="1">
                        <stop offset="0%" stopColor="#22d3ee" stopOpacity="0.32" />
                        <stop offset="100%" stopColor="#22d3ee" stopOpacity="0" />
                      </linearGradient>
                    </defs>
                    <line x1="0" y1="40" x2="600" y2="40" stroke="#1c2748" strokeDasharray="2 4" />
                    <line x1="0" y1="80" x2="600" y2="80" stroke="#1c2748" strokeDasharray="2 4" />
                    <line x1="0" y1="120" x2="600" y2="120" stroke="#1c2748" strokeDasharray="2 4" />
                    <path
                      d="M0,110 L80,80 L160,95 L240,55 L320,82 L400,40 L480,68 L560,30 L600,42 L600,160 L0,160 Z"
                      fill="url(#ar)"
                    />
                    <path
                      d="M0,110 L80,80 L160,95 L240,55 L320,82 L400,40 L480,68 L560,30 L600,42"
                      fill="none"
                      stroke="#22d3ee"
                      strokeWidth="2"
                    />
                  </svg>
                </div>
              </div>
            </div>
          </div>

          <div className="logos">
            <span>OPENAI</span>
            <span>ANTHROPIC</span>
            <span>GEMINI</span>
            <span>GROQ</span>
            <span>LITELLM</span>
            <span>LANGGRAPH</span>
            <span>OPENTELEMETRY</span>
          </div>
        </section>

        <section className="mk-section" id="product">
          <div className="mk-container">
            <span className="mk-eyebrow">A plataforma</span>
            <h2>Tudo para publicar apps LLM sem degradação silenciosa.</h2>
            <p className="lede">
              Tracing, avaliação automática, versionamento de prompts, suítes de regressão, feedback humano e exportação
              de datasets em um único schema e dashboard.
            </p>
            <div className="feature-grid">
              {features.map(({ Icon, title, body, chip }) => (
                <article key={title} className="feature">
                  <div className="feature__icon"><Icon /></div>
                  <h3>{title}</h3>
                  <p>{body}</p>
                  <span className="feature__chip">{chip}</span>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="mk-section mk-section--alt" id="sdk">
          <div className="mk-container">
            <div className="split">
              <div>
                <span className="mk-eyebrow">Python SDK</span>
                <h2>Instrumente an agent in three lines.</h2>
                <p className="lede">
                  Um decorator, um context manager e um uploader em background. O SDK faz batch e retry sem
                  bloquear a requisição do usuário.
                </p>
                <div style={{ marginTop: 28, display: "flex", gap: 12, flexWrap: "wrap" }}>
                  <Link className="mk-btn mk-btn--secondary" href="/docs">
                    <BookOpen />
                    Referência do SDK
                  </Link>
                  <a
                    className="mk-btn mk-btn--ghost"
                    href="https://github.com/rouggerxavier/EvalOps"
                    target="_blank"
                    rel="noreferrer"
                  >
                    <Github />
                    Ver no GitHub
                  </a>
                </div>
              </div>
              <pre className="snippet">
{`# pip install evalops
import evalops
from openai import OpenAI

evalops.init(api_key="evk_live_...", project="docops-agent")
client = OpenAI()

@evalops.trace(name="rag.summarize")
def summarize(question: str, doc: str):
    with evalops.span("retrieve"):
        chunks = retriever(doc, k=8)
    return client.chat.completions.create(
        model="gpt-4o",
        messages=build_prompt(question, chunks),
    )`}
              </pre>
            </div>
          </div>
        </section>

        <section className="mk-section" id="how">
          <div className="mk-container">
            <span className="mk-eyebrow">Como funciona</span>
            <h2>Do tráfego de produção a um deploy testado contra regressões.</h2>
            <div className="steps">
              {steps.map((item) => (
                <div key={item.step} className="step">
                  <div className="step__num">{item.step}</div>
                  <h4>{item.title}</h4>
                  <p>{item.body}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="mk-section">
          <div className="mk-container">
            <div className="cta-card">
              <h2>Pare de debugar seu agente por screenshots.</h2>
              <p>
                Crie um projeto, conecte o SDK e veja seus primeiros traces avaliados fluindo em menos de cinco
                minutos.
              </p>
              <div className="actions-row" style={{ justifyContent: "center" }}>
                <Link className="mk-btn mk-btn--primary mk-btn--lg" href="/register">
                  Crie seu workspace
                  <ArrowRight />
                </Link>
                <Link className="mk-btn mk-btn--secondary mk-btn--lg" href="/login">
                  Entrar
                </Link>
              </div>
            </div>
          </div>
        </section>

        <MarketingFooter />
      </main>
    </div>
  );
}


