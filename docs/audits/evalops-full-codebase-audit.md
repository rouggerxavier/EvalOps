# Auditoria Completa do Codebase — EvalOps

Data: 2026-05-15  
Escopo: backend FastAPI/SQLAlchemy, frontend Next/React, SDK Python, infra, docs, roadmap, baseline, testes e deploy.  
Restrição respeitada: auditoria apenas; nenhum código produtivo, teste ou documentação existente foi alterado.

## 1. Veredito executivo

- **Pode avançar para a próxima subfase?** Parcialmente. Pode avançar apenas para subfase de correção/hardening. Não recomendo iniciar novas funcionalidades antes de fechar os P0/P1 abaixo.
- **Pode fazer deploy?** Não para produção real. Um staging controlado é aceitável se o objetivo for reproduzir os problemas em Postgres e validar correções.
- **O que bloqueia deploy?** Export inclui traces soft-deletados, logout do frontend não revoga JWT no servidor, suíte backend ainda falha por SQLite lock mesmo em blocos pequenos, quota/concurrency não é atomicamente garantida, `npm audit` acusa Next vulnerável, `docker-compose.prod.yml` não aplica Alembic apesar do código já suportar.
- **Nota geral:** 5.6/10.
- **Nota de arquitetura:** 6.2/10.
- **Nota de segurança:** 5.7/10.
- **Nota de testabilidade:** 4.0/10.
- **Nota de readiness para produção:** 4.2/10.

Resumo: o produto tem base funcional e várias fases estão materialmente implementadas, mas o estado real é mais frágil que o roadmap sugere. O risco principal não é falta de feature isolada; é inconsistência entre semântica de dados, UX, testes e deploy.

## 2. Status real por fase

| Fase | Gaps | Status no roadmap | Status no baseline | Status real no código | Testes | Divergências | Veredito |
|---|---|---|---|---|---|---|---|
| Fase 1 | G-02, G-03, G-04, G-17 | Concluída | Concluída | API key flash/cookie e `EVALOPS_API_BASE_URL` existem; fallback bearer é dev-only; body limit e spans cap existem em `apps/api/app/main.py` e `trace_ingest_service.py`. | Frontend security test passou; `test_phase8_p0_security.py` falhou com 4 failed, 1 passed, 4 errors por SQLite lock. | Baseline diz workaround por arquivo; ele não estabiliza este arquivo. | Suspeito |
| Fase 2 | G-01, G-13, G-15, G-16 | Concluída | Concluída | Rate limit por API key/login, audit de failed login e `POST /v1/auth/logout` existem. | `test_phase9_auth_hardening.py`: 11 passed, 1 failed, 3 errors por SQLite lock. | Frontend `logoutAction()` só apaga cookie e não chama `/v1/auth/logout`; tokens sem `jti` continuam aceitos até expirar. | Parcial |
| Fase 3 | G-05 | Concluída | Concluída | `experiment_service.py` usa prompt/model/params das variants e produz saída por variant. | `test_phase5_prompts_datasets_experiments.py`: 8 passed. | Experiments que usam `llm_judge` não passam pelo gate de budget do endpoint de evaluation. | OK com risco |
| Fase 4 | G-06, G-08, G-09, G-10, G-21 | Concluída | Concluída | Audit, redaction opt-in, export download, path absoluto e soft delete existem. | `test_phase10_audit_privacy_exports.py`: 10 passed, 3 failed, 8 errors por SQLite lock. | Exports e dataset build não filtram `Trace.deleted_at`; redaction não cobre eventos/tags/metadata; frontend ainda diz que download não existe. | Parcial/suspeito |
| Fase 5 | G-14, G-18, G-23 | Concluída | Concluída | Paginação cursor em traces; sanitização em server actions; várias ações planejadas marcadas. | `test_phase11_contracts_ux.py`: 5 passed; `npx tsc`, `npm run build`, `npm run test` passaram. | Ainda há botões clicáveis sem handler e páginas exibindo erro bruto (`Detalhe: {error.message}`). | Parcial |
| Fase 6 | G-07, G-11, G-12, G-20, G-25 | Concluída | Concluída | Plan/UsageCounter spans/tokens, duplicate evaluation 409, budget por plano e Postgres URL normalizado existem. | `test_phase12_quota_eval_storage.py`: 15 passed. | Quota check e increment não são atômicos; criação concorrente de `UsageCounter` não trata unique race; LLM judge não consome custo real. | Parcial |
| Fase 7A | Alembic | Parcial/concluída nos docs recentes | Concluída no baseline | `apps/api/alembic/` existe e `alembic upgrade head` em SQLite passou. | Smoke manual: passou. | `docker-compose.prod.yml` ainda diz Alembic não adotado e não seta `EVALOPS_USE_ALEMBIC=1`. Postgres smoke pendente. | Parcial |
| Fase 7B | Services + ownership | Roadmap principal indica pendente; baseline indica executada | Concluída/parcial | `app/ownership.py` e services existem; routers usam alguns services. | Coberta indiretamente pelos testes acima. | `routes_phase5.py` ainda tem wrappers `_project_or_404`; routers seguem grossos; services têm commits e responsabilidades mistas. | Parcial |

## 3. Achados críticos

| ID | Prioridade | Categoria | Arquivo/função/rota | Evidência | Impacto | Recomendação | Fase sugerida |
|---|---|---|---|---|---|---|---|
| A-01 | P0 | Dados/privacidade | `apps/api/app/domain/services/export_service.py:_filter_traces` | Linha 25 filtra só `Trace.project_id`; não aplica `Trace.deleted_at.is_(None)`. | Trace soft-deletado pode reaparecer em export, violando G-21 e expectativa de remoção lógica. | Filtrar deleted em todos os caminhos de export e adicionar teste dedicado. | Antes de deploy |
| A-02 | P1 | Segurança/auth | `apps/web/lib/auth-actions.ts:82` e `apps/api/app/api/routes_auth.py:232` | Frontend logout só chama `clearSessionCookie()`; backend tem denylist JTI mas não é chamado. | Usuário acredita ter encerrado sessão, mas JWT continua válido até expiração se capturado. | Logout do dashboard deve chamar `/v1/auth/logout` com bearer atual antes de limpar cookie. | Antes de deploy |
| A-03 | P1 | Dados/soft delete | `routes_phase5.py:301-309` | `build_dataset_from_traces` busca traces por project/status/env/name, sem `deleted_at`. | Datasets podem incorporar dados removidos logicamente. | Filtrar `Trace.deleted_at.is_(None)` e cobrir com teste. | Antes de deploy |
| A-04 | P1 | Dados/soft delete | `routes_evaluations.py:169-173` | Lista evaluations por projeto via join com Trace, sem excluir `Trace.deleted_at`. | Runs de traces deletados continuam visíveis em visão de projeto. | Adicionar filtro de soft delete ou explicitar endpoint admin. | Próxima subfase |
| A-05 | P1 | Dados/idempotência | `trace_ingest_service.py:60-68` | `_existing_trace_id` não ignora deleted. | Reingest com mesmo `client_trace_id` de trace deletado retorna ID morto e não recria dado válido. | Definir contrato: ignorar deleted, restaurar, ou retornar 409 específico. | Antes de deploy |
| A-06 | P1 | Quota/concurrency | `usage_service.py:100-149` | `enforce_quota()` lê sem lock; `increment_usage()` trava só depois; criação de counter não trata corrida de unique. | Multi-worker/Postgres pode aceitar uso além do plano ou falhar por race. | Unificar check+increment em transação com lock e retry de unique insert. | Antes de tráfego real |
| A-07 | P1 | Consistência transacional | `trace_ingest_service.py:209-218`, `routes_evaluations.py:104-143`, `export_service.py:90-113` | Dados principais são commitados antes de usage/audit em vários fluxos. | Falha após commit gera trace/evaluation/export sem cobrança/usage/audit coerente. | Consolidar transação por use case ou usar outbox/compensação clara. | Antes de deploy |
| A-08 | P1 | Budget/custos | `llm_judge.py:56`, `eval_service.py:66-70`, `experiment_service.py:191-226` | `cost_cap_usd` é lido e não usado; budget soma `EvaluationRun.cost_usd`; experiments chamam evaluators sem gate. | G-12 pode ser contornado ou nunca consumir budget real. | Estimar/registrar custo por chamada e aplicar gate em experiments. | Antes de liberar LLM judge |
| A-09 | P1 | Testabilidade | Testes backend por arquivo | Phase8/9/10 e grupo legado falharam por `sqlite3.OperationalError: database is locked` mesmo com `rm -f evalops.db*`. | Não há gate confiável para regressão; roadmap fica difícil de provar. | Isolar DB por teste/processo, fechar sessions, revisar commits em dependencies e fixtures. | Imediata |
| A-10 | P1 | Dependências | `apps/web/package.json` / `npm audit` | `npm audit` acusa Next vulnerável high e PostCSS moderate; fix sugerido força Next 15.5.18 fora da range. | Deploy web self-hosted fica exposto a advisories de SSRF/cache/XSS/DoS dependendo de uso. | Planejar upgrade controlado de Next/PostCSS e retestar build. | Antes de deploy |
| A-11 | P1 | Deploy/migração | `docker-compose.prod.yml:16-19`, `53-56` | Compose diz Alembic não adotado e sobe uvicorn sem `alembic upgrade head`/`EVALOPS_USE_ALEMBIC`. | Produção pode subir com schema errado ou depender de `create_all` em Postgres. | Atualizar contrato de deploy e exigir migration step. | Antes de deploy |
| A-12 | P2 | Segurança/erros | `trace_ingest_service.py:220-222`, `export_service.py:114-116`, `eval_service.py:184-190`, `api.ts:47-49` | `str(exc)` é persistido/retornado ou exibido. | Erros internos, paths ou dados sensíveis podem vazar para API/UI. | Centralizar sanitização de erros e separar detalhe interno de resposta pública. | Próxima subfase |
| A-13 | P2 | Redaction/PII | `trace_ingest_service.py:137-164` | Redaction cobre `messages_in/out`, `input/output`; não cobre event payload, tags, metadata, user_ref, errors. | Opt-in de PII pode passar falsa sensação de cobertura. | Definir superfície PII e redigir recursivamente campos configuráveis. | Próxima subfase |
| A-14 | P2 | Auth/rate limit | `routes_auth.py:65-68`, `deps.py:65-75` | IP vem só de `request.client`; API key atualiza `last_used_at` em todo request. | Rate limit por IP atrás de proxy pode ficar incorreto; ingest gera write amplification/locks. | Configurar trusted proxy e debounce de `last_used_at`. | Próxima subfase |
| A-15 | P2 | API key lifecycle | `api_key_service.py` / `models.ApiKey` | API keys não têm expiração; scopes são strings arbitrárias; rate limit fixo 60/min. | Menor governança para credenciais em produção. | Validar scopes, suportar expiração e política por plano/projeto. | Pós-MVP hardening |
| A-16 | P2 | Frontend contrato/UX | `exports/page.tsx:517`, `routes_phase6.py:97` | UI afirma que download não existe, mas backend tem `/exports/{id}/download`. | Usuário fica preso copiando path local e não consegue baixar pelo dashboard. | Adicionar client action/link de download e remover microcopy obsoleta. | Próxima subfase |
| A-17 | P2 | SDK confiabilidade | `packages/sdk-python/evalops/uploader.py:30-34`, `73-80` | Queue full, network exception e status HTTP não-2xx são ignorados. | Perda silenciosa de telemetria em produção. | Adicionar retries/backoff, status check, métricas e dead-letter opcional. | Fase 7E/7F |
| A-18 | P2 | Arquitetura | `routes_phase5.py`, `routes.py`, `experiment_service.py`, `eval_service.py` | Routers 421/454 linhas; services 384/269 linhas; import privado `_aggregate`. | Clean Architecture simplificada ficou parcial, com acoplamento e regras espalhadas. | Extrair use cases reais, sem criar repository artificial, e reduzir wrappers. | Fase 7B follow-up |

## 4. Dead code e código órfão

| Arquivo | Símbolo/função/componente/endpoint | Evidência | Por que parece morto | Risco | Recomendação |
|---|---|---|---|---|---|
| `apps/api/app/api/routes_phase5.py` | `_project_or_404`, `_prompt_or_404`, `_dataset_or_404`, `_experiment_or_404` | Linhas 54-70 apenas repassam para `app.ownership`. | Wrappers preservam assinatura antiga após centralização de ownership. | Baixo/médio: dívida e divergência com aceite da Fase 7B. | Remover em refactor específico, trocando chamadas por helper central. |
| `apps/api/app/domain/services/eval_service.py` | `scoreable` | Linha 216 calcula lista nunca usada. | Variável órfã após mudança de agregação. | Baixo: ruído em lógica crítica. | Remover ao tocar no serviço. |
| `apps/api/app/domain/services/eval_service.py` | Primeiro `agg_pairs` | Linhas 219-223 calculam lista e linhas 225-228 sobrescrevem. | Branch morto/contraditório; a condição ainda tem precedência ambígua. | Médio: confunde regra de agregação. | Consolidar regra de agregação com teste. |
| `apps/api/app/domain/evaluators/llm_judge.py` | `cost_cap_usd` | Linha 56 lê config; não há uso posterior. | Campo parece planejado para budget/cap, mas não afeta execução. | Médio/alto: budget por plano fica enganoso. | Implementar ou remover do contrato até existir custo real. |
| `apps/web/app/o/[org]/p/[project]/evaluations/page.tsx` | Botões “Rodar agora”, “Nova evaluation” | Linhas 107-111 sem handler, disabled ou `data-status`. | Ações visuais órfãs; há formulário real mais abaixo. | Médio: regressão G-14 e confiança UX. | Desabilitar/rotular como planned ou conectar à ação real. |
| `apps/web/app/o/[org]/p/[project]/traces/[trace]/page.tsx` | “Flagear”, “Reexecutar”, “Comparar” | Linhas 53-55 sem handler/disabled. | Botões clicáveis sem efeito. | Médio: UX enganosa. | Marcar planned ou remover. |
| `apps/web/app/o/[org]/p/[project]/page.tsx` | “Últimos 7 dias”, “Atualizar”, “Rodar avaliação” | Linhas 108-110 sem handler/disabled. | Controles parecem operacionais, mas não executam ação. | Médio. | Conectar a filtro/refresh/evaluation ou marcar planned. |
| `apps/web/app/o/[org]/p/[project]/exports/page.tsx` | Download via dashboard | Linhas 517-520 dizem que endpoint não existe; backend tem rota em `routes_phase6.py:97`. | UI ficou órfã de contrato backend atual. | Médio/alto: feature implementada no backend não chega ao usuário. | Criar action/link para download autenticado. |
| `apps/web/app/o/[org]/p/[project]/datasets/page.tsx` | “Exportar dataset” disabled sem `data-status` | Linha 512. | Ação planejada não usa marcador consistente. | Baixo. | Padronizar planned state. |
| `apps/web/lib/types.ts` | `OrgSubscription`/`OrgUsage` incompletos | Tipos omitem `monthly_span_limit`, `monthly_token_limit`, `monthly_judge_budget_usd`, `spans_ingested`, `tokens_ingested`; backend retorna em `routes_phase6.py:157-183`. | Contrato frontend defasado. | Baixo/médio: limita UX de quota. | Atualizar tipos quando expor quotas na UI. |
| `docker-compose.prod.yml` | Comentário Alembic não adotado | Linhas 16-19. | Stale depois de `apps/api/alembic/` e `EVALOPS_USE_ALEMBIC`. | Médio/alto para operação. | Atualizar junto do deploy fix. |
| `apps/web/README.md` | `EVALOPS_DASHBOARD_BEARER_TOKEN` required | Linhas 10-14. | Auth real por sessão existe; fallback é dev-only. | Médio: onboarding errado. | Atualizar docs em fase de docs, não agora. |

## 5. Auditoria arquitetural

- **Routers grossos:** `routes.py` tem 421 linhas e ainda monta trace detail, analytics e paginação. `routes_phase5.py` tem 454 linhas e concentra prompts, datasets e experiments. `routes_rubrics.py` e `routes_evaluations.py` estão melhores, mas ainda têm persistência/coordenação relevante.
- **Services bem usados:** `trace_ingest_service.py`, `api_key_service.py`, `export_service.py`, `usage_service.py`, `eval_service.py` e `experiment_service.py` reduziram parte da regra crítica nos routers.
- **Services problemáticos:** `eval_service.run_evaluation()` faz commit interno e dificulta atomicidade do endpoint. `export_service.create_jsonl_export()` faz IO síncrono, quota, audit e commit no mesmo service. `experiment_service.py` tem 384 linhas e chama `_aggregate` privado de `eval_service.py`.
- **Duplicações:** ownership foi centralizado em `app/ownership.py`, mas `routes_phase5.py` mantém wrappers de assinatura antiga. Quota está em `usage_service.py`, mas check e increment são chamados separadamente por services/routers.
- **Violações de camada:** services retornam/lançam `HTTPException` em `export_service.py` e `trace_ingest_service.py`, acoplando domínio/use case ao framework. Para Clean Architecture simplificada, isso é aceitável em MVP, mas deve ser intencional e consistente.
- **Ownership/auth repetidos:** melhorou com `load_project/load_trace/load_export`, mas ainda há `ensure_org_membership` direto em endpoints de org/subscription/usage e patterns antigos em phase5.
- **Risco de overengineering:** ainda não há hexagonal/DDD pesado; o risco atual é o inverso: services grandes e transações espalhadas. Não recomendo criar repository/port/adapter agora.
- **Recomendação arquitetural:** manter a arquitetura simples, mas estabelecer regra: router valida HTTP/deps, service coordena use case sem commit parcial, helpers centralizam ownership/quota/audit. Refactor só onde há bug ou transação crítica.

## 6. Auditoria de segurança

- **Auth/JWT/logout:** JWT com `jti` e `RevokedToken` existe; logout server-side é idempotente. Problema: dashboard não chama `/v1/auth/logout`, então a denylist não protege logout normal. Tokens legados sem `jti` são aceitos até `exp`, comportamento documentado mas ainda risco.
- **API keys:** raw key não aparece em URL; flash cookie one-shot existe no frontend. Backend usa hash Argon2 e prefixo. Gaps: sem expiração, scopes arbitrários, `last_used_at` grava em todo ingest, rate limit fixo.
- **Rate limit:** API key e login existem em memória. Em multi-worker, cada processo terá bucket independente. Login usa IP de `request.client`, sem trusted proxy.
- **Redaction:** opt-in por tag/header existe, mas cobre apenas campos de span selecionados. Eventos, tags, metadata, user_ref e errors podem carregar PII.
- **Audit log:** ações sensíveis existem em vários fluxos; failed login audita email/IP/reason. `record_audit()` engole exceções e não há sanitização central de payload.
- **Secrets/logs/errors:** respostas de ingest/eval/export podem carregar `str(exc)`; frontend `api.ts` preserva texto bruto e algumas páginas exibem `Detalhe: {message}`.
- **Frontend error sanitization:** server actions usam sanitização amigável, mas páginas de load (`keys`, `datasets`, `exports`) ainda exibem mensagens cruas.
- **Riscos remanescentes:** Next vulnerável no `npm audit`; logout sem revoke; export de deleted; proxy/IP; redaction incompleta; in-memory limits sem Redis.

## 7. Auditoria de dados e storage

- **SQLite/Postgres:** app normaliza `postgresql+asyncpg` para `psycopg` e tem helpers de dialeto. SQLite segue problemático nos testes por locks; Postgres real não foi validado nesta auditoria.
- **Migrations/Alembic:** Alembic existe e `alembic upgrade head` em SQLite fresco passou. `docker-compose.prod.yml` não usa `EVALOPS_USE_ALEMBIC=1` nem roda upgrade.
- **UsageCounter:** schema tem spans/tokens; serviço usa `with_for_update()` só em Postgres e só no increment. Check e increment não são atomicamente unidos.
- **Plan:** limites existem, inclusive judge budget. Frontend types não refletem limites novos.
- **Trace.deleted_at:** usado em list/detail/analytics, mas faltam filtros em export, dataset build, evaluations por projeto e idempotência de ingest.
- **RevokedToken:** denylist existe; não encontrei cleanup agendado de tokens expirados.
- **Exports:** path absoluto/configurável existe, download backend existe. O job expõe `file_path` no schema, e o frontend copia path local em vez de baixar arquivo. Export inclui feedback comments e traces soft-deletados.
- **Soft delete:** sem purge físico por design. Falta consistência em todas as consultas.
- **Quota/concurrency:** 402 existe, duplicate evaluation 409 existe, mas concorrência multi-worker/Postgres precisa de prova real e ajuste transacional.

## 8. Auditoria frontend/UX

Observação: a skill/ferramenta “UI UX Pro Max” solicitada não está disponível neste ambiente; a revisão foi manual contra os critérios pedidos.

- **Botões:** ainda há botões com aparência ativa e sem ação em overview, evaluations e trace detail. Isso contraria G-14.
- **Ações planejadas:** várias estão bem marcadas com disabled/`data-status="planned"` em traces, prompts e experiments; datasets tem botão disabled sem marcador.
- **Acessibilidade:** botões com ícones geralmente têm texto visível. Não foi feita varredura automatizada axe/Playwright.
- **Loading/empty/error:** páginas server-rendered têm empty states razoáveis, mas erros de load expõem detalhes brutos.
- **Paginação:** traces tem cursor `next_cursor`; back button permanece planned. Datasets carrega items por dataset via `Promise.all`, potencial N+1.
- **Microcopy:** exports está incorreto: diz que download público não existe, enquanto backend tem endpoint autenticado.
- **Erros sanitizados:** formulários via server actions melhoraram; loads diretos ainda vazam `error.message`.
- **Consistência visual:** build passa; layout parece consistente com app operacional. Problemas principais são confiança e contrato, não estética.
- **Pontos que afetam confiança:** botões sem efeito, file path de servidor exposto ao usuário, logout que não revoga servidor, contadores de traces por status baseados apenas na página atual.

## 9. Auditoria de testes

| Área | Comando executado | Resultado |
|---|---|---|
| Backend env | `python -m pytest ...` | Falhou: `python: command not found`; usado `.venv/bin/python` em seguida. |
| Backend sandbox | blocos pytest com `.venv/bin/python` | Travavam por restrição de sandbox/TestClient; health passou fora do sandbox. |
| Backend Fase 1 | `test_phase8_p0_security.py` | 4 failed, 1 passed, 4 errors, 119.27s; SQLite locked. |
| Backend Fase 2 | `test_phase9_auth_hardening.py` | 11 passed, 1 failed, 3 errors, 169.34s; SQLite locked. |
| Backend Fase 4 | `test_phase10_audit_privacy_exports.py` | 10 passed, 3 failed, 8 errors, 220.51s; SQLite locked. |
| Backend Fase 5 | `test_phase11_contracts_ux.py` | 5 passed, 12.89s. |
| Backend Fase 6 | `test_phase12_quota_eval_storage.py` | 15 passed, 194.78s. |
| Backend Fase 3 | `test_phase5_prompts_datasets_experiments.py` | 8 passed, 132.65s. |
| Backend legado | health/auth/phase1/phase2/phase3/phase6/phase7 group | 14 passed, 1 error, 160.15s; SQLite locked. |
| Backend health extra | `tests/test_health.py` fora do sandbox | 2 passed, 0.48s. |
| Alembic extra | `alembic upgrade head` em SQLite fresco | Passou; criou baseline schema. |
| Frontend typecheck | `npx tsc --noEmit` | Passou. |
| Frontend build | `npm run build` | Passou; Next compilou em 7.0s. |
| Frontend tests | `npm run test` | 1 test file passed, 179ms. |
| npm audit prod | `npm audit --omit=dev` | 2 vulns: Next high, PostCSS moderate. |
| npm audit completo | `npm audit` | Mesmo resultado: 2 vulns. |
| SDK global | `python3 -m pytest -q` | Falhou: `No module named pytest`. |
| SDK sandbox | backend venv | 4 passed, 1 failed por `PermissionError` ao abrir HTTP local. |
| SDK fora sandbox | backend venv | 5 passed, 2.22s. |

Lacunas:

- Testes backend dependem demais de SQLite compartilhado e drop/create por teste, gerando lock.
- Não há teste Postgres real para quota/concurrency.
- Não há teste para export não incluir `deleted_at`.
- Não há teste para frontend chamar logout server-side.
- Não há teste para redaction de events/tags/metadata/user_ref.
- Não há teste SDK para 4xx/5xx, retry, queue full ou dead-letter.
- Testes frontend são mínimos; cobrem segurança/config, não UX/contratos completos.

## 10. Auditoria de deploy

- **Blockers:** `npm audit` high em Next; `docker-compose.prod.yml` sem Alembic; sem smoke Postgres; SQLite lock impede confiança nos gates; logout e exports têm risco de dados/sessão.
- **Envs obrigatórias:** backend produção precisa `APP_ENV=production`, `DATABASE_URL`, `JWT_SECRET`, `EVALOPS_USE_ALEMBIC=1`, limites de body/span, `EVALOPS_EXPORTS_DIR` em storage persistente. Web precisa `EVALOPS_API_BASE_URL` público não-localhost e `EVALOPS_DEV_MODE` ausente.
- **Migrações obrigatórias:** para DB novo, `alembic upgrade head`; para DB legado, `alembic stamp 0001_baseline` exatamente uma vez e depois upgrades normais.
- **npm audit:** Next 15.3.9 está dentro de faixa vulnerável; fix sugerido por npm exigiria versão fora da range atual.
- **Docker/Postgres:** compose usa Postgres 16 e psycopg, mas monta código local e instala deps no boot; não há imagem imutável nem web service. Workers fixos em 1 reduzem risco de quota race, mas não representam produção escalada.
- **Redis/multi-worker:** rate limit é in-memory; multi-worker/multi-instance divide buckets. Redis é documentado em `.env.example`, mas não usado.
- **Riscos antes de tráfego real:** lock/transactions, migration step, vulnerability upgrade, storage persistente para exports, cleanup de revoked tokens/exports expirados e proxy trust.

## 11. Plano de correção recomendado

Correções imediatas:

- Corrigir todos os caminhos que leem traces para respeitar `deleted_at`: export, dataset build, project evaluations, idempotência de ingest.
- Fazer logout frontend chamar `/v1/auth/logout`.
- Tornar testes backend estáveis por arquivo: DB temporário por teste/processo ou fixtures que encerram conexões antes de `drop_all`.
- Atualizar Next/PostCSS com validação de build/test.
- Alinhar `docker-compose.prod.yml` com Alembic real.

Antes da próxima fase:

- Unificar transação de ingest/evaluation/export com usage/audit.
- Ajustar quota check+increment para lock atômico e retry na criação do counter.
- Definir contrato público de erros e remover `str(exc)` de respostas/UX.
- Completar redaction para events/tags/metadata/user_ref.
- Remover wrappers antigos de ownership em `routes_phase5.py`.

Antes de deploy:

- Rodar smoke Postgres de Alembic e quota/concurrency.
- Configurar storage persistente para exports.
- Adicionar cleanup de `RevokedToken` expirado e exports expirados.
- Validar proxy headers/trusted IP para rate limit de login.
- Garantir `EVALOPS_API_BASE_URL` público no web deploy e `EVALOPS_DEV_MODE` ausente.

Pós-MVP:

- API key expiration, scopes validados e rate limit configurável por plano.
- SDK com retries/backoff/dead-letter e telemetria de drops.
- Worker assíncrono para export/evaluation longa.
- Páginas de audit log/admin e histórico de exports.

O que não vale corrigir agora:

- Não criar arquitetura hexagonal/DDD/repositories artificiais.
- Não refatorar todos os routers por estética; priorizar routers ligados a bugs reais.
- Não implementar purge físico antes de fechar semântica de soft delete.
- Não trocar SQLite local por Postgres obrigatório para dev antes de estabilizar fixtures.

## 12. Checklist final

Checklist para continuar desenvolvimento:

- [ ] Corrigir P0/P1 de soft delete/export/logout/quota/testes.
- [ ] Atualizar contratos frontend-backend de exports e usage types.
- [ ] Adicionar testes para cada bug de dados antes de refactor.
- [ ] Remover botões cosméticos ou conectar ações reais.
- [ ] Registrar decisão de transação/commit em services.

Checklist para staging:

- [ ] Rodar Alembic em DB staging vazio.
- [ ] Rodar suíte backend em Postgres staging, incluindo concorrência.
- [ ] Rodar `npm audit`, `npx tsc`, `npm run build`, `npm run test`.
- [ ] Testar login/logout/relogin e revogação JTI.
- [ ] Criar, baixar e expirar export com storage persistente.
- [ ] Validar `EVALOPS_API_BASE_URL` público e cookies secure.

Checklist para produção:

- [ ] `JWT_SECRET` forte e rotacionável.
- [ ] `DATABASE_URL` Postgres com backups.
- [ ] `EVALOPS_USE_ALEMBIC=1` ou migration job antes do app.
- [ ] `EVALOPS_EXPORTS_DIR` em volume persistente com retenção.
- [ ] Next/PostCSS fora de advisories altas.
- [ ] Rate limit compatível com multi-worker/proxy.
- [ ] Monitoramento de erros, audit failures, quota failures e SDK ingestion drops.
- [ ] Plano de rollback de migration e deploy documentado.
