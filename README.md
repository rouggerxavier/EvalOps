# EvalOps Studio

**Controle de qualidade para agentes de IA.** Defina um Quality Gate por projeto
para acompanhar qualidade das respostas, alucinação/grounding, custo, latência e
regras críticas, com resultado aprovado, revisão necessária ou reprovado.

A base técnica continua sendo LLMOps: tracing, avaliações com rubricas, workflows
de prompts e experimentos e feedback humano.

## Stack

- **API**: FastAPI + SQLAlchemy + Alembic (`apps/api/`)
- **Web**: Next.js 15 App Router + Server Components + Server Actions + CSS puro (`apps/web/`)
- **SDK**: `evalops-python` (`packages/sdk-python/`)
- Sem Tailwind, sem shadcn, sem CSS-in-JS. Apenas `lucide-react` no frontend.

## Quality Gate

- Overview: card com métricas, limites, amostras e resultado em PT-BR.
- Settings: configuração persistente por projeto.
- API: GET/PUT de configuração e GET de status calculado.
- [Arquitetura, contrato, limites e roteiro de demonstração](docs/quality-gate.md).

## Fases entregues

- Phase 1: identity, orgs, projects, API keys
- Phase 2: trace ingestion + SDK Python
- Phase 3: trace dashboard (overview/list/detail)
- Phase 4: rubrics + sync evaluations
- Phase 5: prompts, datasets, experiments
- Phase 6: feedback, exports, usage/quota
- Phase 7: MVP hardening + release prep
- **Phase 8 (atual)**: refatoração interna idêntica ao preview cockpit (branch `tentativa_refactor`) — novos endpoints (attention, coverage, sdk-status, trace flags, rerun, compare, notifications, rag consolidado, evaluation summary, prompt usage, exports listing, members, project patch) e UI reescrita 1:1.

## Layout

```text
apps/
  api/                FastAPI backend
  web/                Next.js dashboard
packages/
  sdk-python/         evalops-python SDK
docs/
  plans/              planos de execução
  ops/                operação (migrations do banco)
  audits/             auditorias de código e produto
evalops-preview/      fonte visual do redesign (referência, não buildado)
```

## Quickstart local

### 1) API
```bash
cd apps/api
python -m venv .venv && source .venv/bin/activate
pip install -c requirements.lock -e .[dev]
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

### 2) Seed
```bash
python scripts/seed_dev.py
```

### 3) Web
```bash
cd apps/web
npm install
npm run dev
```

Abrir `http://localhost:3000`. Login com a conta seed (`dev@local`/`devpassword`).

## Testes

```bash
# Backend
cd apps/api && pytest

# Web
cd apps/web && npm run test
```

## Docs

- [Índice da documentação atual](docs/README.md)
- [Quality Gate e demonstração](docs/quality-gate.md)
- [Plano desta entrega](docs/plans/quality-gate.md)
- [Migrations do banco](docs/ops/database-migrations.md)
- `evalops-preview/DESIGN_NOTES.md` (referência visual)

## Atalhos do app

| Combo | Tela |
|---|---|
| `G O` | Visão geral |
| `G T` | Traces |
| `G E` | Avaliações |
| `G X` | Experimentos |
| `G P` | Prompts |
| `G R` | Rubricas |
| `G D` | Datasets |
| `G K` | Chaves API |
| `G S` | Settings |
| `⌘K` / `/` | Focar busca |
| `?` | Lista de atalhos |

### Convites e gestão de membros

Convites exigem JWT pessoal e owner atual, com viewer como papel padrão e prazo
fixo de 24 horas. `EVALOPS_INVITATIONS_ENABLED=false` mantém emissão e worker
desligados mesmo com SMTP de recuperação configurado; leitura, revogação, aceite
de links existentes e gestão de membros continuam disponíveis. Novos envios
exigem SMTP/origem/Redis válidos e worker com `send_invitation_job` registrado.
A emissão limita cada par organização/owner a dez pedidos por 300 segundos,
sem fallback em memória. Retorno 503 pode significar envio já iniciado: confira a
lista antes de reemitir. Contenção retorna 409 `membership_conflict`; repita apenas
por um novo pedido explícito.

Migração, invariantes, testes dedicados e rollback: [R2](docs/security/r2-invitations-memberships.md).
