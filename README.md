# EvalOps Studio

LLMOps cockpit for trace observability, rubric-based evaluations, prompt & experiment
workflows, and human feedback — opinionated, dark, dense.

## Stack

- **API**: FastAPI + SQLAlchemy + Alembic (`apps/api/`)
- **Web**: Next.js 14 App Router + Server Components + Server Actions + CSS puro (`apps/web/`)
- **SDK**: `evalops-python` (`packages/sdk-python/`)
- Sem Tailwind, sem shadcn, sem CSS-in-JS. Apenas `lucide-react` no frontend.

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
  plans/              planos de execução (este arquivo: refatoração_identica.md)
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

- `docs/04-system-architecture.md`
- `docs/07-api-spec.md`
- `docs/11-dashboard-and-analytics.md`
- `docs/plans/refatoração_identica.md` (plano da refatoração atual)
- `evalops-preview/DESIGN_NOTES.md` (direção visual e decisões de UX)

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
