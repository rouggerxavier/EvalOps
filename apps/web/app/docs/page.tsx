import { BookOpen, Code2, FileJson, Github } from "lucide-react";

import styles from "@/app/publicMarketingPages.module.css";
import LightPillar from "@/components/LightPillar";
import { MarketingFooter } from "@/components/MarketingFooter";
import { MarketingNav } from "@/components/MarketingNav";

const RAW_API_BASE = process.env.EVALOPS_API_BASE_URL ?? "http://localhost:8000/v1";
const API_ROOT = RAW_API_BASE.endsWith("/v1") ? RAW_API_BASE.slice(0, -3) : RAW_API_BASE;

const cards = [
  {
    title: "Refer\u00EAncia da API",
    description: "Abra a documenta\u00E7\u00E3o FastAPI de todos os endpoints do EvalOps.",
    href: `${API_ROOT}/docs`,
    Icon: BookOpen,
    external: true,
  },
  {
    title: "OpenAPI JSON",
    description: "Use o schema bruto para gera\u00E7\u00E3o de c\u00F3digo, testes ou SDKs.",
    href: `${API_ROOT}/openapi.json`,
    Icon: FileJson,
    external: true,
  },
  {
    title: "Quickstart do SDK Python",
    description: "Instrumente agentes com traces, spans e upload em background.",
    href: "https://github.com/rouggerxavier/EvalOps/tree/main/packages/sdk-python",
    Icon: Code2,
    external: true,
  },
  {
    title: "Especifica\u00E7\u00F5es do produto",
    description: "Leia as especifica\u00E7\u00F5es e o plano de implementa\u00E7\u00E3o do reposit\u00F3rio.",
    href: "https://github.com/rouggerxavier/EvalOps/tree/main/docs",
    Icon: Github,
    external: true,
  },
];

export default function DocsPage() {
  return (
    <div className="mk-shell">
      <div className="bg-stage">
        <div className="bg-pillar" aria-hidden="true">
          <LightPillar
            topColor="#5aa3ff"
            bottomColor="#1a2a7a"
            intensity={1.02}
            rotationSpeed={0.18}
            glowAmount={0.0078}
            pillarWidth={2.85}
            pillarHeight={0.34}
            noiseIntensity={0.5}
            pillarRotation={130}
            interactive={false}
            mixBlendMode="screen"
            quality="medium"
          />
        </div>
        <div className="bg-grid" />
      </div>
      <MarketingNav />
      <main className={`mk-wrap ${styles.publicMain}`}>
        <section className={`mk-section ${styles.pageSection}`}>
          <div className={`mk-container ${styles.pageContainer}`}>
            <header className={styles.heroBlock}>
              <span className={`mk-eyebrow ${styles.eyebrow}`}>{"Guias t\u00E9cnicos"}</span>
              <h1 className={styles.title}>{"Documenta\u00E7\u00E3o"}</h1>
              <p className={styles.subtitle}>
                {
                  "Guias de implementa\u00E7\u00E3o, refer\u00EAncia da API e especifica\u00E7\u00F5es oficiais para operar o EvalOps Studio em produ\u00E7\u00E3o."
                }
              </p>
            </header>

            <div className={styles.docsGrid}>
              {cards.map(({ title, description, href, Icon, external }) => (
                <a
                  key={title}
                  className={styles.docsCard}
                  href={href}
                  target={external ? "_blank" : undefined}
                  rel={external ? "noreferrer noopener" : undefined}
                >
                  <div className={styles.docsCardIcon}>
                    <Icon />
                  </div>
                  <h2 className={styles.docsCardTitle}>{title}</h2>
                  <p className={styles.docsCardDescription}>{description}</p>
                  <span className={styles.docsCardCta}>{"Abrir refer\u00EAncia "}&rarr;</span>
                </a>
              ))}
            </div>

            <section className={styles.codeCard} aria-label={"Exemplo de instrumenta\u00E7\u00E3o com SDK Python"}>
              <div className={styles.codeCardHeader}>
                <div className={styles.codeDots} aria-hidden="true">
                  <span />
                  <span />
                  <span />
                </div>
                <span className={styles.codeLang}>Python SDK</span>
                <span className={styles.codeMeta}>sdk_quickstart.py</span>
              </div>
              <pre className={styles.codeBlock}>
{`# pip install evalops
import evalops
from openai import OpenAI

evalops.init(api_key="evk_live_...", project="docops-agent", environment="prod")
client = OpenAI()

@evalops.trace(name="rag.answer")
def answer(question: str):
    with evalops.span("retrieve", type="tool"):
        chunks = retriever(question)
    return client.responses.create(
        model="gpt-4o-mini",
        input=build_prompt(question, chunks),
    )`}
              </pre>
            </section>
          </div>
        </section>
        <MarketingFooter />
      </main>
    </div>
  );
}
