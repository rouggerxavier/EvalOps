# EvalOps Studio

Plataforma de avaliação e qualidade de sistemas de IA, com interface web e operação programática. Hoje a implementação concentra-se em aplicações generativas e agentes instrumentados. A evolução para ML tradicional, Deep Learning e uso por agentes de programação está **especificada, ainda não implementada**.

## Capacidades atuais e limites

- Traces/spans, rubricas YAML versionadas, avaliações determinísticas/LLM-as-judge e feedback humano.
- Quality Gate por projeto, métricas de qualidade/custo/latência e estados pass/review/fail com evidências.
- Prompts, datasets, experimentos com histórico, exports, cotas e avaliação por amostragem.
- API `/v1`, SDK Python, organizações/projetos e chaves com scopes ingest/read/evaluate.
- Experimentos atuais **sintetizam respostas** a partir de templates; não executam o modelo candidato.
- Replay atual repete **uma chamada LLM**; não reexecuta ferramentas, memória ou agente completo.

Estado auditado em `545149b`: [diagnóstico e evidências](docs/audits/estado-real-2026-11-09.md). Ausência de métricas ou custo não significa zero.

## Evolução proposta

Núcleo de avaliação por tarefa, snapshots de datasets, métricas tipadas, comparação e interfaces para humanos/agentes. Primeira entrega planejada: regressão offline com predições importadas pela web/API. CLI, MCP, runner de aplicações, classificação e DL são fases futuras.

[Visão de produto](PRODUCT.md) · [Arquitetura proposta](docs/architecture/evolucao.md) · [SPECs](docs/specs/README.md) · [Roadmap](docs/plans/roadmap-evolucao.md)

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

## Estado da entrega

A main inclui tracing, avaliações, prompts/datasets, experimentos sintéticos, feedback, exports, Quality Gate, replay de chamada LLM, cotas, amostragem e melhorias de autorização/conta. Branches locais e relatórios posteriores não são automaticamente funcionalidades da main. Consulte o [inventário](docs/audits/estado-real-2026-11-09.md) para limites e validação por capacidade.

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
- [Plano histórico do Quality Gate](docs/plans/quality-gate.md)
- [Roadmap da evolução proposta](docs/plans/roadmap-evolucao.md)
- [Especificações técnicas](docs/specs/README.md)
- [Migrations do banco](docs/ops/database-migrations.md)
- [Sistema visual atual](DESIGN.md)
- `evalops-preview/DESIGN_NOTES.md` (referência histórica)

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

### Regressão offline — F0 e primeira vertical F1

A implementação de tarefas acrescenta snapshots imutáveis, modelos externos declarados, predições importadas e métricas tipadas. API, SDK/CLI e a página **Avaliações → Regressão offline** consultam os mesmos resultados persistidos. A comparação usa pares do mesmo snapshot e preserva a leitura legada por opt-in `view=task_v1`.

Antes do rollout, aplique a migration 0014. Escopo, limites, testes e rollback estão em [F0/F1](docs/plans/f0-implementation-progress.md); as [SPECs](docs/specs/README.md) continuam como referência de evolução.

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
