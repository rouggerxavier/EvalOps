# E2E Smoke (Playwright)

Smoke E2E para cada rota refatorada na Phase 8 (`tentativa_refactor`).

## Pré-requisitos

1. API rodando em `http://localhost:8000` com seed dev (`my-org` / `my-project`):
   ```bash
   cd apps/api
   uvicorn app.main:app --port 8000 &
   python scripts/seed_dev.py
   ```
2. Web rodando em `http://localhost:3000`:
   ```bash
   cd apps/web
   npm install
   npm run dev
   ```
3. Browsers Playwright:
   ```bash
   npx playwright install chromium
   ```

## Rodar

```bash
cd apps/web
npm run test:e2e
```

## Variáveis de ambiente

| Var | Default |
|---|---|
| `E2E_BASE_URL` | `http://localhost:3000` |
| `E2E_API_BASE_URL` | `http://localhost:8000/v1` |
| `E2E_ORG_SLUG` | `my-org` |
| `E2E_PROJECT_SLUG` | `my-project` |
| `E2E_EMAIL` / `E2E_PASSWORD` | credenciais E2E (cria usuário novo via `/auth/register` se não existir) |

## O que cobre

Para cada uma das 11 rotas (`overview`, `traces`, `traces/compare`, `evaluations`,
`prompts`, `rubrics`, `datasets`, `experiments`, `keys`, `exports`, `settings`),
verifica:

- Render OK (status 2xx)
- `h1.page-header__title` com texto esperado
- Sem error boundary visível

Cobre também o atalho global `G T` → `/traces`.
