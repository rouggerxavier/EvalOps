# 16 — Deployment & DevOps

## 1. Topologia hosted (default MVP)

```
                   evalops.studio
                        │
            ┌───────────┴────────────┐
            ▼                        ▼
   app.evalops.studio       api.evalops.studio
   (Vercel — Next.js)       (Fly.io — FastAPI)
                                     │
                  ┌──────────────────┼──────────────────┐
                  ▼                  ▼                  ▼
            Neon (Postgres)   Upstash (Redis)    Cloudflare R2
                                     │
                              Fly worker (Arq)
                                  Fase 1.1
```

**Justificativas:**
- **Vercel** (web): zero-config Next.js 15, edge cache, preview deploys per-PR.
- **Fly.io** (api/worker): app-specific scaling, regiões próximas (gru, gig, mia), suporta long-running workers.
- **Neon** (Postgres): branching de DB por preview, pgvector se necessário, free tier generoso.
- **Upstash** (Redis): pay-per-request, tem REST API quando necessário.
- **Cloudflare R2** (storage): sem egress fee — economia em downloads de export.

Alternativa "all-in-one": **Railway** (web+api+postgres+redis em um projeto). Mais simples, menos flexível.

## 2. Environments

| Env | DB | Redis | LLM keys | Domínio |
|---|---|---|---|---|
| `local` | Postgres em Docker | Redis em Docker | dev keys do autor | `localhost` |
| `preview` | Neon branch (auto) | Upstash dev DB | dev keys | `*.vercel.app` + `*.fly.dev` |
| `staging` | Neon `staging` branch | Upstash staging | staging keys | `staging.evalops.studio` |
| `prod` | Neon `main` | Upstash prod | prod keys | `evalops.studio` |

Migrations: aplicadas automaticamente em deploy via job pre-release (Alembic upgrade head).

## 3. Local dev — `docker-compose.yml`

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment: { POSTGRES_PASSWORD: dev, POSTGRES_DB: evalops }
    ports: ["5432:5432"]
    volumes: [pgdata:/var/lib/postgresql/data]
  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
  api:
    build: ./apps/api
    env_file: ./apps/api/.env.local
    depends_on: [postgres, redis]
    ports: ["8000:8000"]
    command: uvicorn app.main:app --reload --host 0.0.0.0
  worker:
    build: ./apps/api
    env_file: ./apps/api/.env.local
    depends_on: [redis, postgres]
    command: arq app.workers.WorkerSettings
    profiles: ["worker"]   # opt-in (Fase 1.1)
  web:
    build: ./apps/web
    env_file: ./apps/web/.env.local
    depends_on: [api]
    ports: ["3000:3000"]
volumes:
  pgdata:
```

Comandos:
```bash
docker compose up -d           # MVP (sem worker)
docker compose --profile worker up -d
make seed                       # popula dev
make test                       # roda toda a stack de testes
```

## 4. CI/CD

### 4.1 GitHub Actions

```yaml
name: ci
on: [push, pull_request]
jobs:
  lint:        ...
  test-api:    services: [postgres, redis]; uv run pytest -q --cov
  test-web:    pnpm test
  test-sdk:    matrix: [3.9, 3.10, 3.11, 3.12]; uv run pytest packages/sdk-python
  build-api:   docker buildx; tag with sha
  build-web:   pnpm build
```

Apenas em `main`:
```yaml
deploy-api:    flyctl deploy -a evalops-api
deploy-worker: flyctl deploy -a evalops-worker
deploy-web:    Vercel deploy hook
publish-sdk:   uv build && uv publish (Test PyPI no MVP, PyPI real em Fase 2)
```

### 4.2 Migrations
- Pre-deploy job: `alembic upgrade head` contra DB do environment.
- Em prod, exige aprovação manual (Environment protection rule).

### 4.3 Rollback
- Fly.io: `flyctl releases rollback <n>` (ou via UI).
- Vercel: clique em build anterior → "Promote to production".
- DB: migrations devem ser **backwards-compatible** (adicionar colunas nullable; remover é em duas releases).

## 5. Configuração & secrets

### 5.1 Variáveis de ambiente (chave: API)

```env
# Core
APP_ENV=prod                          # local|staging|prod
LOG_LEVEL=INFO
SECRET_KEY=...                        # JWT signing
SESSION_SECRET=...                    # Auth.js cookie

# DB
DATABASE_URL=postgresql+asyncpg://...
DATABASE_POOL_SIZE=10

# Redis
REDIS_URL=rediss://...

# Storage
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_BUCKET=evalops-exports-prod
R2_PUBLIC_URL=https://exports.evalops.studio

# LLM providers
OPENAI_API_KEY=...
GEMINI_API_KEY=...
GROQ_API_KEY=...
ANTHROPIC_API_KEY=...

# Auth
GITHUB_CLIENT_ID=...
GITHUB_CLIENT_SECRET=...
RESEND_API_KEY=...                    # email magic link

# Observability
SENTRY_DSN_API=...
SENTRY_DSN_WEB=...
PROMETHEUS_PORT=9090
```

### 5.2 Local: `.env.example`

Comitado no repo, sem valores reais. README orienta como preencher.

### 5.3 Hosted: secrets manager
- Fly: `flyctl secrets set KEY=value -a evalops-api`.
- Vercel: dashboard → Project → Settings → Environment Variables.
- Rotação: anual (manual no MVP); SECRET_KEY com kid e suporte a 2 chaves simultâneas.

## 6. Observabilidade

### 6.1 Logs
- `structlog` em JSON.
- Campos obrigatórios: `request_id`, `org_id`, `project_id` (quando aplicável), `user_id`, `level`, `event`, `timestamp`.
- **Nunca** logar conteúdo de prompts/respostas (NFR-33).
- Drains: stdout → Fly logs → opcional drain para Logtail/Better Stack.

### 6.2 Metrics (Prometheus)
- `/metrics` exposto na API.
- Métricas:
  - `http_request_duration_seconds{path,method,status}` (histogram).
  - `traces_ingested_total{project_id}` (counter).
  - `evaluation_runs_total{rubric,status}` (counter).
  - `worker_queue_depth{queue}` (gauge).
  - `judge_cost_usd_total{model}` (counter).

Scrape: Grafana Cloud free tier.

### 6.3 Traces (OpenTelemetry)
- API instrumentada com `opentelemetry-instrumentation-fastapi`.
- Exporter OTLP → Honeycomb (free tier) ou Grafana Tempo.
- Sample 10% em prod, 100% em staging.

### 6.4 Errors
- Sentry para api e web (DSNs separados).
- Source maps no frontend.
- Ignore-list de erros conhecidos (network do cliente, etc).

### 6.5 Uptime
- UptimeRobot ou Better Uptime monitorando `https://api.evalops.studio/health`.

## 7. Health checks

```
GET /health/liveness    → 200 sempre que processo está vivo
GET /health/readiness   → 200 só se DB e Redis respondem
```

Fly.io aponta para `/health/readiness`. Restart em 3 falhas seguidas.

## 8. Backups & disaster recovery

| Recurso | Estratégia | RPO/RTO |
|---|---|---|
| Postgres | Neon PITR 7 dias + dump mensal para R2 | RPO 1h, RTO 1h |
| Redis | Sem backup (cache + queue: aceitável perder) | N/A |
| R2 (exports) | Versioning ON, retenção 30 dias | RPO 24h |
| Código | GitHub | inerente |

DR drill: trimestral, restaurar Postgres em ambiente isolado e validar.

## 9. Cost guardrails

| Item | Estimativa MVP |
|---|---|
| Vercel hobby | $0 |
| Fly.io api (shared-cpu-1x) | ~$5/mo |
| Fly.io worker | ~$5/mo (Fase 1.1) |
| Neon free | $0 |
| Upstash free | $0 |
| R2 (storage + class B ops) | < $1/mo no MVP |
| LLM judges (Groq + Gemini) | $5-20/mo (cap em código) |
| **Total MVP** | **< $30/mo** |

Em escala (1000 clientes): mover Postgres para hard-tier ($30+), Redis pago, possivelmente ClickHouse — fora do escopo MVP.

## 10. Domain & DNS

- `evalops.studio` registrado em Cloudflare.
- DNS via Cloudflare:
  - `evalops.studio` (A) → landing page (Vercel ou estática).
  - `app.evalops.studio` (CNAME) → Vercel.
  - `api.evalops.studio` (CNAME) → Fly.io.
  - `docs.evalops.studio` (CNAME) → GitHub Pages ou Vercel.
- TLS: gerenciado pelos providers (Let's Encrypt).

## 11. Releases

- Versionamento semver para SDK (`evalops-python`).
- API versionada via prefixo `/v1`. Breaking → `/v2`.
- Web: deploy contínuo, sem versão pública.
- CHANGELOG.md mantido em raiz; `/changelog` no site faz fetch.

## 12. Open questions

- **[Decisão pendente]** Multi-region desde o início? Recomendação: **não**, single-region (`gru`) no MVP; multi-region em Fase 3.
- **[Decisão pendente]** Self-hosted (docker-compose) como produto vendido? Recomendação: **publicar imagens Docker** em Fase 2; vender suporte só em Fase 3+.
- **[Decisão pendente]** Helm chart para K8s? Recomendação: **não** — overkill para o porte do MVP.
