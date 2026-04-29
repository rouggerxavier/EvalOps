# EvalOps Studio

> Mini-SaaS de **LLMOps / AgentOps** para tracing, avaliação automática, versionamento de prompts/modelos e melhoria contínua de aplicações com LLMs e agentes.

EvalOps Studio é a camada de **observabilidade, governança e qualidade** para aplicações de IA. Permite instrumentar agentes e apps com poucas linhas de código (SDK Python oficial), capturar traces ricos (prompt, resposta, ferramentas, tokens, custo, latência, fallback, erro), avaliar respostas com rubricas configuráveis (LLM-as-judge + heurísticas), comparar versões de prompt/modelo em testes de regressão e exportar datasets para fine-tuning ou few-shot.

Pensado para servir de **camada de operação** sobre projetos como **DocOps Agent**, **Aurora Support AI** e **Agente ImobiliarIA** — e para demonstrar competência sênior em AI Engineering / LLMOps em contexto de portfólio.

---

## Status atual

🚧 **Fase: Spec Driven Development.** O projeto está em fase de especificação. **Nenhuma implementação ainda.** A documentação completa está em [`docs/`](docs/README.md).

## Por onde começar

1. [`docs/00-project-overview.md`](docs/00-project-overview.md) — visão de produto e problema.
2. [`docs/03-mvp-scope.md`](docs/03-mvp-scope.md) — o que está dentro e fora do MVP.
3. [`docs/04-system-architecture.md`](docs/04-system-architecture.md) — arquitetura macro.
4. [`docs/14-implementation-roadmap.md`](docs/14-implementation-roadmap.md) — plano de execução em fases.
5. [`docs/decisions/`](docs/decisions/) — ADRs (Architecture Decision Records).

## Stack alvo (resumo)

- **Backend / API:** FastAPI + Python 3.12, Pydantic v2, SQLAlchemy 2 (async), Alembic.
- **Workers:** Arq (Redis-based, async-native). _Fase 1.1._
- **Banco:** PostgreSQL 16 (Neon). Redis (Upstash) para fila/cache/rate-limit.
- **Frontend:** Next.js 15 (App Router) + TypeScript + Tailwind + shadcn/ui + Recharts.
- **Auth:** Auth.js (NextAuth v5) com Email magic link + GitHub OAuth.
- **LLM providers:** abstração via `litellm`. Default judges: OpenAI (`gpt-4o-mini`, `gpt-4.1`), Gemini (`gemini-2.5-flash`), Groq (`llama-3.3-70b`) para evals baratos.
- **SDK oficial:** `evalops-python` (decorator `@trace`, cliente HTTP, contexto async).
- **Deploy:** Vercel (frontend), Fly.io ou Railway (API + workers), Neon (Postgres), Upstash (Redis).
- **Observabilidade do próprio EvalOps:** OpenTelemetry, logs estruturados (structlog), Sentry.

> Justificativa completa em [`docs/decisions/ADR-0001-tech-stack.md`](docs/decisions/ADR-0001-tech-stack.md).

## Contribuindo / explorando o projeto

Este é um projeto de portfólio em fase de design. Sugestões e revisões de spec são bem-vindas via Issues ou PRs em `docs/`.

## Licença

A definir antes da primeira implementação. Default proposto: **MIT** para o SDK e **PolyForm Noncommercial** ou similar para o backend/frontend (caso o autor queira manter direito comercial). Ver [`docs/17-risks-tradeoffs-and-open-questions.md`](docs/17-risks-tradeoffs-and-open-questions.md).
