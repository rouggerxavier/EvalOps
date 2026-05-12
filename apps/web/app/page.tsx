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
            <span>v0.4 &middot; Tracing + LLM-as-judge em produção</span>
            <span className="arrow">&rsaquo;</span>
          </span>
          <h1>
            Observabilidade e <em>avaliação</em>
            <br />
            para aplicações de IA.
          </h1>
          <p className="hero__lede">
            Rastreie cada chamada de LLM. Avalie cada resposta com rubricas declarativas. Compare prompts e
            modelos em tráfego real. Envie para produção com confiança &mdash; sem torcer.
          </p>
          <div className="hero__cta">
            <Link className="mk-btn mk-btn--primary mk-btn--lg" href="/register">
              Começar grátis
              <ArrowRight />
            </Link>
            <Link className="mk-btn mk-btn--secondary mk-btn--lg" href="/docs">
              <BookOpen />
              Ler documentação
            </Link>
          </div>
          <div className="hero__meta">
            <span>
              <code>pip install evalops</code>
            </span>
            <span className="dot" />
            <span>SDK Python &middot; compatível com OpenTelemetry &middot; pronto para self-hosting</span>
          </div>

          <div className="hero__preview">
            <div className="dash-mock">
              <aside className="dash-mock__sidebar">
                <div className="dash-mock__brand">
                  <img src="/brand/mark-evalops.svg" style={{ width: 18, height: 18 }} alt="" />
                  EvalOps
                </div>
                <div className="dash-mock__nav">
                  <div className="item active"><span className="dot" />Visão geral</div>
                  <div className="item"><span className="dot" />Traces</div>
                  <div className="item"><span className="dot" />Avaliações</div>
                  <div className="item"><span className="dot" />Rubricas</div>
                  <div className="item"><span className="dot" />Experimentos</div>
                  <div className="item"><span className="dot" />Datasets</div>
                  <div className="item"><span className="dot" />Prompts</div>
                  <div className="item"><span className="dot" />Chaves API</div>
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
                  <div className="dash-mock__kpi"><div className="l">Traces</div><div className="v">128,547</div><div className="d">&uarr; 18.6%</div></div>
                  <div className="dash-mock__kpi"><div className="l">Score médio</div><div className="v">0.86</div><div className="d">&uarr; 6.3%</div></div>
                  <div className="dash-mock__kpi"><div className="l">Latência P95</div><div className="v">2.48s</div><div className="d">&darr; 9.7%</div></div>
                  <div className="dash-mock__kpi"><div className="l">Custo</div><div className="v">$1,842</div><div className="d">&darr; 14.2%</div></div>
                </div>
                <div className="dash-mock__chart">
                  <div className="head">
                    <span className="t">Traces ao longo do tempo</span>
                    <span>Diário &#9662;</span>
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
            <h2>Tudo o que você precisa para enviar apps com LLM sem degradação silenciosa.</h2>
            <p className="lede">
              Tracing, avaliação automatica, versionamento de prompts, suítes de regressão, feedback humano e
              exportação de datasets &mdash; uma stack, um esquema, um dashboard.
            </p>
            <div className="feature-grid">
              <article className="feature">
                <div className="feature__icon"><Activity /></div>
                <h3>Tracing estruturado para agentes</h3>
                <p>
                  Capture a árvore completa &mdash; chamadas de LLM, ferramentas, retrievals e fallbacks
                  &mdash; com tokens, custo e latência em cada span. Feito para agentes multietapa.
                </p>
                <span className="feature__chip">FR-20 &middot; FR-25</span>
              </article>
              <article className="feature">
                <div className="feature__icon"><Gauge /></div>
                <h3>Rubricas como código</h3>
                <p>
                  Declare qualidade em YAML. LLM-as-judge, regex, schema-valid, cosine similarity e exact
                  match &mdash; tudo composto e versionado junto com seus prompts.
                </p>
                <span className="feature__chip">FR-30 &middot; FR-31 &middot; FR-33</span>
              </article>
              <article className="feature">
                <div className="feature__icon"><GitCompare /></div>
                <h3>Experimentos e regressão</h3>
                <p>
                  Rode um golden set contra duas variantes de prompt/modelo. Veja pass rate, custo e latência
                  lado a lado. Bloqueie deploys no CI quando houver regressão de qualidade.
                </p>
                <span className="feature__chip">FR-42 &middot; FR-43 &middot; FR-44</span>
              </article>
              <article className="feature">
                <div className="feature__icon"><ThumbsUp /></div>
                <h3>Feedback que vira dado de treino</h3>
                <p>
                  Thumbs e revisões humanas entram no seu dataset. Exporte JSONL em formato chat ou
                  HuggingFace &mdash; faça fine-tune no que seus usuários realmente aprovaram.
                </p>
                <span className="feature__chip">FR-60 &middot; FR-63 &middot; FR-64</span>
              </article>
              <article className="feature">
                <div className="feature__icon"><DollarSign /></div>
                <h3>Custo visível por padrão</h3>
                <p>
                  Cada span tem custo em USD. Agrupe por modelo, projeto, ambiente ou usuário. Descubra o
                  prompt que está queimando $400/dia sem você perceber.
                </p>
                <span className="feature__chip">FR-50 &middot; FR-53</span>
              </article>
              <article className="feature">
                <div className="feature__icon"><ShieldCheck /></div>
                <h3>Esquema pronto para privacidade</h3>
                <p>
                  Redação, retenção e direito ao esquecimento fazem parte do modelo de dados desde o início.
                  Repositórios prontos para RLS, API keys com hash e trilha de auditoria.
                </p>
                <span className="feature__chip">NFR-21 &middot; NFR-30 &middot; NFR-31</span>
              </article>
            </div>
          </div>
        </section>

        <section className="mk-section mk-section--alt" id="sdk">
          <div className="mk-container">
            <div className="split">
              <div>
                <span className="mk-eyebrow">SDK Python</span>
                <h2>Instrumente um agente em três linhas.</h2>
                <p className="lede">
                  Um decorator, um context manager, um flush. O SDK roda em background com batching e retry
                  exponencial &mdash; e nunca bloqueia a requisição do usuário, mesmo quando o EvalOps cai.
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
              <div>
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
          </div>
        </section>

        <section className="mk-section" id="how">
          <div className="mk-container">
            <span className="mk-eyebrow">Como funciona</span>
            <h2>Do tráfego em produção ao deploy com regressão testada.</h2>
            <div className="steps">
              <div className="step">
                <div className="step__num">PASSO 01</div>
                <h4>Instrumentar</h4>
                <p>
                  Adicione o SDK ou envie POST para{" "}
                  <code style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--accent-cyan)" }}>
                    /v1/traces
                  </code>
                  . Spans, ferramentas e eventos entram em streaming.
                </p>
              </div>
              <div className="step">
                <div className="step__num">PASSO 02</div>
                <h4>Avaliar</h4>
                <p>As rubricas rodam na ingestão ou manualmente. Cada trace recebe score, reasoning e pass/fail.</p>
              </div>
              <div className="step">
                <div className="step__num">PASSO 03</div>
                <h4>Comparar</h4>
                <p>
                  Rode um experimento entre prompt v1 e v2. Veja pass rate, latência e custo no mesmo painel.
                </p>
              </div>
              <div className="step">
                <div className="step__num">PASSO 04</div>
                <h4>Melhorar</h4>
                <p>
                  Promova a variante melhor. Exporte traces com thumbs-up como dataset JSONL para fine-tune ou
                  few-shot.
                </p>
              </div>
            </div>
          </div>
        </section>

        <section className="mk-section">
          <div className="mk-container">
            <div className="cta-card">
              <h2>Pare de depurar seu agente por screenshot.</h2>
              <p>
                Crie um projeto, conecte o SDK no seu app e tenha seus primeiros traces avaliados fluindo em
                menos de cinco minutos.
              </p>
              <div
                style={{
                  display: "inline-flex",
                  gap: 12,
                  flexWrap: "wrap",
                  justifyContent: "center",
                  position: "relative",
                }}
              >
                <Link className="mk-btn mk-btn--primary mk-btn--lg" href="/register">
                  Criar espaço de trabalho
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

