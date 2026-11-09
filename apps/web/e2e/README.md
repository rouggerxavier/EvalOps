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
- H1 com o título atual em pt-BR
- Sem error boundary visível
- Layout em 1280×900 e 375×900 sem rolagem lateral da página

Cobre também o atalho global `G T` → `/traces` e a gaveta móvel com Enter,
Tab/Shift+Tab, Escape, retorno de foco, navegação e mudança para desktop.

O usuário de `E2E_EMAIL` precisa ser membro da organização/projeto configurados;
criar automaticamente outro usuário não concede acesso ao workspace do seed.

Convites/memberships: a fixture de contrato é local, fica só em memória e não usa SMTP,
Redis ou banco. Em três terminais dentro de `apps/web`:

```sh
E2E_INVITATIONS=1 node e2e/invitations-fake-api.mjs
EVALOPS_API_BASE_URL=http://127.0.0.1:18145/v1 npm run dev -- --port 13145
E2E_INVITATIONS=1 E2E_BASE_URL=http://127.0.0.1:13145 npm run test:e2e -- e2e/invitations.spec.ts
```

A suíte cobre owner/member/viewer, confirmações por teclado em 375/1280 px,
conflito controlado, expiração e segredo no fragmento. Ela verifica o contrato web;
a prova integrada com backend real e mailbox fake continua sendo um gate separado.
