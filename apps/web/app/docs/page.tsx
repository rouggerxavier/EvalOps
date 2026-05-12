import { BookOpen, Code2, FileJson, Github } from "lucide-react";

import { MarketingFooter } from "@/components/MarketingFooter";
import { MarketingNav } from "@/components/MarketingNav";

const RAW_API_BASE = process.env.EVALOPS_API_BASE_URL ?? "http://localhost:8000/v1";
const API_ROOT = RAW_API_BASE.endsWith("/v1") ? RAW_API_BASE.slice(0, -3) : RAW_API_BASE;

const cards = [
  {
    title: "Referência da API",
    description: "Abra a documentação FastAPI de todos os endpoints do EvalOps.",
    href: `${API_ROOT}/docs`,
    Icon: BookOpen,
    external: true,
  },
  {
    title: "OpenAPI JSON",
    description: "Use o schema bruto para geração de código, testes ou SDKs.",
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
    title: "Especificações do produto",
    description: "Leia as especificações e o plano de implementação do repositório.",
    href: "https://github.com/rouggerxavier/EvalOps/tree/main/docs",
    Icon: Github,
    external: true,
  },
];

export default function DocsPage() {
  return (
    <div className="mk-shell">
      <div className="bg-stage"><div className="bg-grid" /></div>
      <MarketingNav />
      <main className="mk-wrap public-page">
        <section className="mk-section">
          <div className="mk-container">
            <span className="mk-eyebrow">Referência</span>
            <h1 className="public-title">Documentação</h1>
            <p className="lede">Guias de implementação, referência da API e especificações do EvalOps Studio.</p>

            <div className="feature-grid public-card-grid">
              {cards.map(({ title, description, href, Icon, external }) => (
                <a
                  key={title}
                  className="feature public-card"
                  href={href}
                  target={external ? "_blank" : undefined}
                  rel={external ? "noreferrer" : undefined}
                >
                  <div className="feature__icon"><Icon /></div>
                  <h3>{title}</h3>
                  <p>{description}</p>
                  <span className="feature__chip">Abrir referência</span>
                </a>
              ))}
            </div>

            <pre className="snippet public-snippet">
{`# pip install evalops
import evalops

evalops.init(api_key="evk_live_...", project="docops-agent", environment="prod")

@evalops.trace(name="rag.answer")
def answer(question: str):
    with evalops.span("retrieve", type="tool"):
        chunks = retriever(question)
    return llm_answer(question, chunks)`}
            </pre>
          </div>
        </section>
        <MarketingFooter />
      </main>
    </div>
  );
}


