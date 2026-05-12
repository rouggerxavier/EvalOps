# EvalOps Studio

EvalOps Studio is a portfolio-first LLMOps platform for:

- trace ingestion and observability
- rubric-based evaluations
- prompt/dataset/experiment workflows
- human feedback and JSONL export

The project is spec-driven (`docs/`) and implemented in this monorepo.

## Phase status

- Phase 1: identity, orgs, projects, API keys
- Phase 2: trace ingestion + SDK Python
- Phase 3: trace dashboard (overview/list/detail)
- Phase 4: rubrics + sync evaluations
- Phase 5: prompts, datasets, experiments
- Phase 6: feedback, exports, usage/quota mocks
- Phase 7: MVP hardening and release prep (current)

## Repository layout

```text
apps/
  api/               # FastAPI backend
  web/               # Next.js dashboard
packages/
  sdk-python/        # evalops-python SDK
docs/                # product, architecture, roadmap, ADRs
```

## Local quickstart

### 1) API

```bash
cd apps/api
python -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 2) Seed dev workspace

```bash
python scripts/seed_dev.py
```

### 3) Web

```bash
cd apps/web
npm install
npm run dev
```

Open:

- Dashboard: `http://localhost:3000/o/my-org/p/my-project`
- API docs: `http://localhost:8000/docs`

## Validation commands

### Backend tests

```bash
pytest apps/api/tests -q
```

### SDK tests

```bash
pytest packages/sdk-python/tests -q
```

### Web build

```bash
cd apps/web && npm run build
```

### Hosted smoke (phase 7)

```bash
python apps/api/scripts/smoke_hosted.py --base-url http://localhost:8000
```

## Documentation map

- Product overview: [docs/00-project-overview.md](docs/00-project-overview.md)
- MVP scope: [docs/03-mvp-scope.md](docs/03-mvp-scope.md)
- API spec: [docs/07-api-spec.md](docs/07-api-spec.md)
- Roadmap: [docs/14-implementation-roadmap.md](docs/14-implementation-roadmap.md)
- Acceptance checklist: [docs/21-mvp-acceptance-checklist.md](docs/21-mvp-acceptance-checklist.md)
- Phase gates: [docs/22-phase-gates-and-validation.md](docs/22-phase-gates-and-validation.md)
- Codebase audit: [docs/24-codebase-audit.md](docs/24-codebase-audit.md)
