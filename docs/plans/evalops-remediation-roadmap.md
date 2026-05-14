# Roadmap de Correção — EvalOps

Data: 2026-05-13
Fonte: `docs/audits/evalops-important-rules-audit.md`
Status: Fases 0, 1 e 3 concluídas. Fase 2 pendente (refazer). Demais em planejamento.
Branch alvo: `main`.

## Status por fase

| Fase | Estado | Evidência |
|---|---|---|
| 0 — Baseline | ✅ Concluída (2026-05-13) | `docs/plans/baseline.md` |
| 1 — P0 segurança/configuração | ✅ Re-implementada (2026-05-14) | G-02, G-03, G-04, G-17 fechados; 5/5 testes backend (test_phase8_p0_security.py) + 13/13 testes web (tests/security.test.mjs); regressão backend 10/10 verde. Frontend tsc/build não executado nesta sessão (Node ausente — ver baseline.md). |
| 2 — Rate limit e hardening de auth | ⚠️ Pendente (refazer) | Marcada como concluída no histórico antigo, mas código G-01/G-13/G-15/G-16 não presente neste checkout. Bloqueia Fase 4. |
| 3 — Experiments reais | ✅ Concluída (2026-05-14) | G-05 fechado; 8/8 testes phase5 (test_phase5_prompts_datasets_experiments.py), baseline obrigatório 28/28 verde, validação adicional 5/5 verde (phase3/6/7) |
| 4 — Audit log, privacy, exports | ⏳ Pendente | — |
| 5 — Contratos UX | ⏳ Pendente | — |
| 6 — Robustez quota/eval/storage | ⏳ Pendente | — |
| 7 — Arquitetura e manutenção | ⏳ Pendente | — |

---

## 1. Resumo executivo

### Estado atual
EvalOps é um MVP funcional com fundamentos sólidos (auth com argon2/JWT, idempotência de traces, quotas mensais, evaluation engine com rubrics versionadas, exports JSONL, audit log parcial). A auditoria identificou **30 gaps** (G-01 a G-30) distribuídos em 4 níveis de severidade:

- **P0 (5 gaps)**: vazamento de segredo, rate limit ausente, configuração frágil em prod, comparação A/B fake.
- **P1 (13 gaps)**: hardening de auth, audit log incompleto, quotas finas, redaction, exports inacessíveis, contratos front/back desalinhados.
- **P2 (8 gaps)**: paginação, observabilidade, migrations, race condition em quota, soft delete, contratos.
- **P3 (4 gaps)**: SDK retry, expiração de key, polish.

Notas da auditoria: maturidade arquitetural **5/10**, cobertura de regras **5/10**, segurança **5/10**.

### Por que não corrigir tudo de uma vez
1. **Risco de regressão amplificado**: tocar segurança + arquitetura + contratos simultaneamente impede bisect quando algo quebrar.
2. **Inversão de prioridade**: refatoração arquitetural antes dos P0 deixa o produto **organizado e vulnerável**. Segurança primeiro, beleza depois.
3. **Custo cognitivo**: 30 gaps em um único PR é impossível de revisar; quebrar em fases pequenas mantém revisões úteis.
4. **Validação progressiva**: cada fase precisa estabilizar (testes verdes, smoke em dev) antes da próxima — caso contrário acumulamos dívida disfarçada de progresso.
5. **MVP pré-revenue**: ainda não há volume real; otimizar para *correção de regras críticas*, não para reescrita.

### Estratégia geral
- Corrigir **gaps de segurança P0** antes de qualquer outra coisa.
- Hardening de auth e enforcement de quotas como **segunda onda**.
- Funcionalidade prometida na UI (experiments, exports, paginação) como **terceira onda** — destrava valor de produto sem mexer em segurança.
- Audit log + privacy como **quarta onda** — exigido por compliance, mas não-bloqueante para uso interno.
- Frontend cosmético + contratos como **quinta onda** — UX limpa antes de demo externa.
- Arquitetura (extração de services, Alembic, observabilidade) como **última onda**, somente depois que as regras estão corretas. Refatorar código quebrado primeiro consolida bugs.

### Ordem recomendada das fases
0. **Baseline e proteção contra regressão** (descoberta de comandos, snapshot de testes verdes).
1. **P0 segurança/configuração**: G-02, G-03, G-04, G-17.
2. **Rate limit e hardening de auth**: G-01, G-13, G-15, G-16.
3. **Experiments reais**: G-05.
4. **Audit log, privacy e exports**: G-06, G-08, G-09, G-10, G-21.
5. **Contratos frontend↔backend e UX funcional**: G-14, G-18, G-23.
6. **Robustez de quota/evaluation/storage**: G-07, G-11, G-12, G-20, G-25.
7. **Arquitetura, observabilidade e manutenção**: extração de services, Alembic, structured logs, G-22, G-26, G-27.

### Riscos que precisam ser tratados antes de tráfego pago
- G-02 (key leak em URL) — secret em logs e histórico do navegador.
- G-03 (fallback bearer estático) — bypass de login.
- G-04 (base URL localhost em prod) — dashboard quebrado silenciosamente.
- G-01 (rate limit ausente) — abuso de quota por key válida.
- G-13 (sem rate limit em /login) — bruteforce.
- G-17 (payload sem limite) — DoS por body gigante.
- G-15 (logout não invalida JWT) — sessão fantasma após "sair".

Fases 1 e 2 são o **mínimo pré-tráfego pago**. Demais fases podem rodar pós-lançamento controlado.

---

## 2. Princípios de execução

Regras obrigatórias para todas as fases de implementação:

1. **Uma fase por vez.** Não abrir PR que mistura escopos de duas fases distintas. Fase só termina quando todos os critérios de aceite estão verdes.
2. **Preservar contratos públicos.** Não renomear endpoints, headers, campos de schema, nem alterar status codes de paths estáveis sem migração explícita. Mudança de contrato exige nota na fase e deprecation path.
3. **Sem refatoração arquitetural antes dos P0/P1.** Não extrair services, não mover arquivos, não renomear pastas até a Fase 7. Corrigir comportamento primeiro; arrumar a casa depois. Exceção: criar arquivo novo (ex: `rate_limit_service.py`) é permitido se a fase exigir.
4. **Não misturar frontend, backend e domínio.** Se a fase é backend-only, não tocar `apps/web`. Se é frontend-only, não alterar Python. Quando ambos forem inevitáveis (G-02, G-04, G-14), separar em commits distintos dentro do mesmo PR.
5. **Sempre adicionar ou ajustar testes.** Nenhum gap fechado sem teste. Bug fix → teste de regressão. Feature → teste de aceite. Mudança de contrato → snapshot atualizado.
6. **Sempre rodar validações mínimas.** Cada fase tem matriz de comandos definida no item 4. Falha de qualquer comando bloqueia merge.
7. **Não implementar features futuras fora do escopo.** Se durante a Fase 2 surge ideia para a Fase 6, anotar como follow-up — não puxar para a Fase 2.
8. **Documentar riscos remanescentes.** Cada fase encerra com seção "o que fica para depois" no PR. Sem essa seção, fase está incompleta.
9. **Comando de validação parametrizado.** Comandos exatos descobertos na Fase 0 viram referência para todas as próximas. Não inventar comandos novos sem registrar.
10. **Rollback explícito.** Cada fase tem plano de reverter sem perda de dados (revert + migration down quando aplicável).

---

## 3. Fases recomendadas

> Estrutura detalhada por fase está no item 4. Esta seção é o resumo de cada fase.

### Fase 0 — Baseline e proteção contra regressão
- Descobrir e registrar comandos reais de teste/build/typecheck (Python e Web).
- Confirmar quais testes passam hoje (snapshot verde).
- Criar checklist de validação mínima reutilizável.
- Sem mudanças de código produtivo.

### Fase 1 — P0 segurança/configuração
- G-02: raw API key não pode aparecer em URL.
- G-03: fallback bearer token só em dev.
- G-04: `EVALOPS_API_BASE_URL` localhost deve falhar em prod.
- G-17: payload size limit e cap de spans por trace.

### Fase 2 — Rate limit e hardening de auth
- G-01: rate limit por API key (enforced).
- G-13: rate limit em `/login`.
- G-15: logout server-side (denylist ou TTL curto).
- G-16: audit de `auth.failed_login`.

### Fase 3 — Experiments reais
- G-05: variants influenciam execução (prompt/model por variant).
- Teste de divergência entre variants.

### Fase 4 — Audit log, privacy e exports
- G-06: audit log em ações sensíveis (api_key, rubric, evaluation, trace.delete).
- G-08: redaction opt-in via tag/header.
- G-09: endpoint `GET /v1/exports/{id}/download`.
- G-10: `EVALOPS_EXPORTS_DIR` absoluto e configurável.
- G-21: soft delete de traces + audit.

### Fase 5 — Contratos frontend↔backend e UX funcional
- G-14: botões cosméticos (conectar ou marcar "em breve").
- G-18: paginação real com cursor estável.
- G-23: saneamento de mensagens de erro no frontend.
- Alinhar loading/empty/error com respostas reais.

### Fase 6 — Robustez de quota/evaluation/storage
- G-07: quota por spans e tokens.
- G-11: duplicate evaluation → 409.
- G-12: judge budget por plano.
- G-20: lock pessimista no usage counter.
- G-25: Postgres para produção (manter SQLite em dev/test).

### Fase 7 — Arquitetura e manutenção
- Extrair `trace_ingest_service`, `export_service`, `api_key_service`, `experiment_service`.
- Consolidar helper `_project_or_404` em `deps.get_owned_project()`.
- Adotar Alembic (G-19).
- Structured logging com request_id (G-22).
- Polish: G-26 (key expiration), G-27 (SDK retry), G-29 (auto-refresh).

---

## 4. Detalhamento por fase

### Fase 0 — Baseline e proteção contra regressão

- **Objetivo**: garantir que existe uma linha de base verde antes de mudar qualquer regra.
- **Gaps cobertos**: nenhum (preparatória).
- **Prioridade**: Crítica.
- **Risco**: Baixo (sem mudanças de código produtivo).
- **Dependências**: nenhuma.
- **Arquivos prováveis**:
  - Leitura: `apps/api/pyproject.toml`, `apps/web/package.json`, `docker-compose.yml`, `Makefile` (se existir), `README*`.
  - Saída: `docs/plans/baseline.md` com a matriz de comandos descobertos.
- **Mudanças esperadas**:
  - Documento de baseline com comandos validados.
  - Lista de testes que passam hoje e tempo de execução.
  - Checklist de validação por fase (reutilizável).
- **Mudanças proibidas**: nenhuma alteração em código produtivo.
- **Testes necessários**: rodar suíte existente sem mudanças.
- **Comandos de validação** (descobrir e registrar reais; abaixo é hipótese a confirmar):
  - Backend: `pytest apps/api/tests -q`
  - SDK: `pytest packages/sdk-python -q` (se existir suíte)
  - Web typecheck: `pnpm --filter web typecheck`
  - Web lint: `pnpm --filter web lint`
  - Web build: `pnpm --filter web build`
  - Web tests (se existirem): `pnpm --filter web test`
- **Critérios de aceite**:
  - Documento `docs/plans/baseline.md` commitado.
  - Todos os comandos da matriz executados e resultado registrado (verde / falha conhecida).
  - Falhas pré-existentes (se houver) catalogadas como "dívida prévia" — não bloqueiam fase 0, mas viram input para fase 1.
- **Rollback strategy**: revert do documento; sem efeito em runtime.
- **O que fica para depois**: qualquer correção de teste flake observada vira ticket para a fase apropriada.

---

### Fase 1 — P0 segurança/configuração

- **Objetivo**: parar leaks ativos e impedir bypass de configuração.
- **Gaps cobertos**: G-02, G-03, G-04, G-17.
- **Prioridade**: P0 — bloqueante para tráfego pago.
- **Risco**: Médio (G-02 muda fluxo de UI de criação de key; G-17 pode rejeitar payloads legítimos se cap mal calibrado).
- **Dependências**: Fase 0.
- **Arquivos prováveis**:
  - G-02: `apps/web/lib/actions.ts`, `apps/web/app/o/[org]/p/[project]/keys/page.tsx`, possivelmente um helper de cookie flash em `apps/web/lib/`.
  - G-03: `apps/web/lib/auth.ts`.
  - G-04: `apps/web/lib/api.ts`, `apps/web/lib/auth.ts`.
  - G-17: `apps/api/app/main.py` (middleware), `apps/api/app/api/routes.py` (validação de span count), possivelmente `apps/api/app/schemas.py`.
- **Mudanças esperadas**:
  - G-02: raw key passa a ser entregue via cookie HttpOnly de uso único OU server session efêmera com claim token de curto TTL. URL nunca contém `key=evk_...`.
  - G-03: `hasFallbackToken()` retorna `false` em `NODE_ENV === "production"`, independente do env. Documentar nova flag `EVALOPS_DEV_MODE=1` para dev local.
  - G-04: módulo `api.ts` valida no boot — `throw` se `NODE_ENV=production` e base começa com `http://localhost` ou `http://127.`.
  - G-17: middleware ASGI cap em 8 MB (configurável via env). Validação adicional: `len(payload.traces) <= 50`, `len(trace.spans) <= 500` por trace.
- **Mudanças proibidas**:
  - Refatorar `actions.ts` para arquitetura nova.
  - Renomear `EVALOPS_API_BASE_URL`.
  - Mudar contrato de `POST /v1/traces` (apenas adicionar validação).
- **Testes necessários**:
  - E2E web (Playwright/Vitest): criar key, asserta que URL e Referer não contêm `evk_`.
  - Unit web: `hasFallbackToken()` em ambiente prod retorna `false`.
  - Unit web: import de `api.ts` em prod sem env → throw.
  - Integ API: payload > 8MB → 413. Trace com 501 spans → 422.
- **Comandos de validação**:
  - `pytest apps/api/tests -q`
  - `pnpm --filter web typecheck && pnpm --filter web test && pnpm --filter web test:e2e`
- **Critérios de aceite**:
  - Network panel após criar key: nenhum request 3xx com `key=` na query.
  - Build de prod com `EVALOPS_API_BASE_URL` ausente falha (CI).
  - Payload de 10 MB → `413`. Trace com 1000 spans → `422`.
- **Rollback strategy**:
  - Cada gap em commit separado dentro do PR → revert granular se quebrar staging.
  - G-17 cap configurável por env (`EVALOPS_MAX_BODY_MB`, `EVALOPS_MAX_SPANS_PER_TRACE`) para tunar sem deploy.
- **O que fica para depois**:
  - Limites finos por plan (G-07) vão para Fase 6.
  - Telemetria de payload rejeitado fica para Fase 7.

---

### Fase 2 — Rate limit e hardening de auth

- **Objetivo**: impedir abuso de API key e bruteforce de login.
- **Gaps cobertos**: G-01, G-13, G-15, G-16.
- **Prioridade**: P0/P1 — bloqueante para tráfego pago.
- **Risco**: Médio (logout server-side muda comportamento de sessões existentes).
- **Dependências**: Fase 1.
- **Arquivos prováveis**:
  - G-01: `apps/api/app/deps.py`, novo `apps/api/app/domain/services/rate_limit_service.py`, possivelmente nova tabela `ApiKeyUsageMinute` em `models.py` (ou implementação in-memory para MVP).
  - G-13: `apps/api/app/api/routes_auth.py`, reuso de `rate_limit_service`.
  - G-15: `apps/api/app/api/routes_auth.py` (novo `POST /v1/auth/logout`), `apps/api/app/security.py` (denylist ou redução de TTL + refresh).
  - G-16: `apps/api/app/api/routes_auth.py` (emit audit em failed_login).
- **Mudanças esperadas**:
  - G-01: sliding window por `api_key_id`, default 60 req/min (já no schema), retorna 429 com `Retry-After`. Persistência: tabela leve OU dict in-memory com warning de "single-worker". Para MVP single-worker, in-memory aceitável; documentar limitação.
  - G-13: limite por `email + IP`, 5 tentativas / 5 min → 429.
  - G-15: `POST /v1/auth/logout` invalida o JWT atual (denylist por `jti` em tabela `RevokedToken` com TTL = `exp`). Cleanup cron pode ficar para depois.
  - G-16: cada 401 em `/login` gera `AuditLog(action="auth.failed_login", payload={email, ip})`.
- **Mudanças proibidas**:
  - Trocar JWT por sessão server-side (refactor maior — fica para fase 7).
  - Mudar formato/claims do JWT existente além de adicionar `jti` se ainda não tiver.
- **Testes necessários**:
  - Integ: 61 calls/min com 1 key → 429.
  - Integ: 6 logins errados em 1 min → 429.
  - Integ: login, capturar token, `POST /logout`, reusar token → 401.
  - Integ: 3 logins errados → 3 audit rows com `action="auth.failed_login"`.
- **Comandos de validação**:
  - `pytest apps/api/tests -q -k "rate_limit or auth"`
  - `pytest apps/api/tests -q`
- **Critérios de aceite**:
  - Todos os 4 testes acima verdes.
  - 401 de bruteforce continua retornando mensagem genérica (não revela existência do email).
- **Rollback strategy**:
  - Feature flag `EVALOPS_RATE_LIMIT_ENABLED` (default true). Em incidente, set `false` e reiniciar.
  - Denylist em tabela separada: drop da tabela revoga o efeito.
- **O que fica para depois**:
  - Distribuir rate limit para multi-worker (Redis) — Fase 7.
  - 2FA — fora de escopo.
  - Refresh token rotation — Fase 7.

---

### Fase 3 — Experiments reais

- **Objetivo**: corrigir comparação A/B falsa. Variants precisam influenciar prompt/model.
- **Gaps cobertos**: G-05.
- **Prioridade**: P0 — feature visível na UI está mentindo matematicamente.
- **Risco**: Alto (mudança de comportamento; testes phase5 existentes podem precisar atualização).
- **Dependências**: Fase 0. Independente de fases 1 e 2 em código, mas em PR deve vir depois.
- **Arquivos prováveis**:
  - `apps/api/app/api/routes_phase5.py` (refatoração de `_execute_experiment`).
  - Novo `apps/api/app/domain/services/experiment_service.py`.
  - Possivelmente extender schema `ExperimentVariantIn` com `prompt_version_ref` e `model`.
  - `apps/api/tests/test_phase5_prompts_datasets_experiments.py` (atualizar / adicionar caso).
- **Mudanças esperadas**:
  - Cada `ExperimentVariant` carrega referência a `prompt_version` e/ou `model`.
  - `experiment_service.run(experiment, db)` executa: para cada item × variant → resolver prompt da variant → produzir output (mock LLM aceitável se infra já tiver) → rodar rubric sobre output → registrar score.
  - Comparações vs baseline ficam matematicamente reais.
  - **Não** introduzir worker assíncrono nem fila (síncrono OK para MVP).
- **Mudanças proibidas**:
  - Mudar formato de `comparisons` ou `criteria_failures` no response (consumidores existem).
  - Tocar UI nesta fase além do estritamente necessário para evitar quebrar página `/experiments` em estado vazio.
- **Testes necessários**:
  - Integ: experiment com 2 variants e prompts distintos produz `delta_pass_rate != 0` em rubric determinístico simples.
  - Integ: experiment com 2 variants idênticas produz `delta_pass_rate == 0` (regressão controlada).
  - Smoke: rodar experimento existente em teste atual (atualizar fixtures se variant precisar de prompt_version_ref).
- **Comandos de validação**:
  - `pytest apps/api/tests/test_phase5_prompts_datasets_experiments.py -q`
  - `pytest apps/api/tests -q`
- **Critérios de aceite**:
  - 2 variants distintas produzem scores distintos.
  - Página `/experiments` continua carregando sem erro 500.
- **Rollback strategy**:
  - Service novo isolado; revert do PR restaura comportamento atual.
- **O que fica para depois**:
  - Execução assíncrona com fila — Fase 7.
  - Variant com config de evaluators distinta — fora de escopo.

---

### Fase 4 — Audit log, privacy e exports

- **Objetivo**: compliance e download funcional de exports.
- **Gaps cobertos**: G-06, G-08, G-09, G-10, G-21.
- **Prioridade**: P1.
- **Risco**: Médio (G-10 muda caminho de exports — migrar arquivos existentes; G-21 muda semântica de DELETE).
- **Dependências**: Fase 0. Pode rodar em paralelo com Fase 3 (escopos independentes), **mas em PRs separados**.
- **Arquivos prováveis**:
  - G-06: helper em `apps/api/app/models.py` (ex: `record_audit()`) ou novo `apps/api/app/domain/services/audit_service.py`. Aplicado em: `routes.py` (api_key create/revoke, trace delete), `routes_rubrics.py`, `routes_phase5.py` (rubric/experiment/prompt/dataset writes), `routes_evaluations.py`.
  - G-08: novo `apps/api/app/domain/services/redaction_service.py`, alteração em `routes.py:228` (ingest) para aplicar redaction quando `tags.pii=true` ou header `X-EvalOps-Redact` presente.
  - G-09: `apps/api/app/api/routes_phase6.py` — novo `GET /v1/exports/{id}/download` com `StreamingResponse` + check de `expires_at`.
  - G-10: novo `apps/api/app/config.py` exportando `EXPORTS_DIR` resolvido a partir de env (`EVALOPS_EXPORTS_DIR`) com default absoluto.
  - G-21: `apps/api/app/models.py` (campo `Trace.deleted_at`), `apps/api/app/api/routes.py` (DELETE soft + audit), filtros de list `Trace.deleted_at IS NULL`.
- **Mudanças esperadas**:
  - Audit log cobrindo: `api_key.created`, `api_key.revoked`, `rubric.created`, `rubric_version.created`, `prompt_version.created`, `dataset.created`, `experiment.run`, `evaluation.run`, `trace.deleted`.
  - Endpoint de download de export retorna `application/x-ndjson`, 410 se expirado, 404 se inexistente.
  - Exports gravados em `EVALOPS_EXPORTS_DIR` (default `${repo}/apps/api/storage/exports` resolvido absoluto). Aceitar override.
  - Soft delete: `Trace.deleted_at` setado; `GET /v1/traces` filtra por default; novo flag `?include_deleted=true` opcional (somente admin) — opcional, **pode ficar para depois**.
- **Mudanças proibidas**:
  - Mudar formato de `AuditLog` existente.
  - Mudar contrato de criação de export.
  - Implementar TTL/retenção de traces nesta fase (fora de escopo).
- **Testes necessários**:
  - Integ: cada write listado acima cria 1 audit row.
  - Integ: ingest com `tags.pii=true` esconde `messages_in/out` em GET subsequente.
  - Integ: criar export → polling status → `GET /download` retorna JSONL bytes.
  - Integ: export expirado → 410.
  - Integ: rodar API em CWD diferente, export grava em path absoluto correto.
  - Integ: DELETE trace → list não retorna; row no DB tem `deleted_at`; audit registrado.
- **Comandos de validação**:
  - `pytest apps/api/tests -q -k "audit or redaction or export or soft_delete"`
  - `pytest apps/api/tests -q`
- **Critérios de aceite**:
  - Cobertura de audit log expandida verificada por teste matricial.
  - Download funciona end-to-end.
  - Path de exports independente de CWD.
- **Rollback strategy**:
  - `record_audit()` é fire-and-forget (não bloqueia request principal) — falha no audit não derruba a operação.
  - Soft delete: revert mantém rows com `deleted_at` no DB; queries antigas voltam a usar `WHERE 1=1` — sem perda.
  - Migração de path: script idempotente que move arquivos existentes para o novo dir.
- **O que fica para depois**:
  - Cleanup automático de exports expirados (cron) — Fase 7.
  - `GET /v1/audit-logs` (leitura) — Fase 5 ou 7.
  - Redaction automática por heurística (sem opt-in) — fora de escopo.
  - Hash/tokenization de `user_ref` — fora de escopo MVP.

---

### Fase 5 — Contratos frontend↔backend e UX funcional

- **Objetivo**: alinhar UI ao backend real. Sem botões mentirosos.
- **Gaps cobertos**: G-14, G-18, G-23.
- **Prioridade**: P1/P2.
- **Risco**: Baixo a médio (paginação real pode quebrar consumidores que ignoram cursor).
- **Dependências**: Fase 4 (G-09 download é pré-requisito para conectar botão "Exportar JSONL").
- **Arquivos prováveis**:
  - G-14: `apps/web/app/o/[org]/p/[project]/traces/page.tsx`, e auditar `datasets/`, `exports/`, `prompts/`, `experiments/`.
  - G-18: `apps/api/app/api/routes.py` (list_traces e demais lists), `apps/web/lib/api.ts` (passar/usar cursor).
  - G-23: `apps/web/lib/actions.ts` — `messageFromActionError` com whitelist.
- **Mudanças esperadas**:
  - G-14: cada botão visível conectado (Exportar JSONL → flow de criação + download da Fase 4; Refresh → re-fetch) OU marcado `disabled` com tooltip "em breve" + tag `data-status="planned"`.
  - G-18: cursor baseado em `(created_at, id)` em base64. `next_cursor` populado quando há mais resultados. Backend lê via query param `cursor`. Frontend usa botões prev/next reais.
  - G-23: erros não-conhecidos viram mensagem genérica ("Algo deu errado, tente novamente"). Whitelist registra mensagens conhecidas (validação, 401, 402, 409, 429).
- **Mudanças proibidas**:
  - Adicionar features novas de UI fora da auditoria.
  - Mudar layout/visual além do necessário para conectar funcionalidade.
- **Testes necessários**:
  - E2E: cada botão visível em `traces`, `datasets`, `exports`, `prompts`, `experiments` — checa `data-status="planned"` ou tem handler.
  - Integ + E2E: 250 traces, lista paginada navega 3 páginas e retorna ao começo.
  - Unit web: `messageFromActionError(new Error("DETAIL: SELECT * FROM users"))` retorna mensagem genérica.
- **Comandos de validação**:
  - `pnpm --filter web test && pnpm --filter web test:e2e && pnpm --filter web typecheck`
  - `pytest apps/api/tests -q -k "pagination or list_traces"`
- **Critérios de aceite**:
  - Nenhum botão sem ação ou marcação.
  - Paginação navega ida-e-volta com mesmo conjunto.
  - Mensagens de erro no front nunca contêm stack/SQL.
- **Rollback strategy**:
  - Mudanças isoladas por componente; revert granular.
  - Cursor opcional — backend continua aceitando ausência (retorna primeira página).
- **O que fica para depois**:
  - Polling automático (G-29) — Fase 7.
  - Ordenação configurável (G-no-id, P3) — fora.
  - SWR / cache lado cliente — fora.

---

### Fase 6 — Robustez de quota/evaluation/storage

- **Objetivo**: limites finos e correção de race conditions. Postgres em prod.
- **Gaps cobertos**: G-07, G-11, G-12, G-20, G-25.
- **Prioridade**: P1/P2.
- **Risco**: Alto (mudança de storage de prod; lock pessimista muda perfil de concorrência).
- **Dependências**: Fase 0. Idealmente após Fase 4 (audit registra quota events).
- **Arquivos prováveis**:
  - G-07: `apps/api/app/models.py:Plan` (campos `monthly_span_limit`, `monthly_token_limit`), `apps/api/app/domain/services/usage_service.py`, `apps/api/app/api/routes.py` (post-ingest enforcement).
  - G-11: `apps/api/app/api/routes_evaluations.py`, `apps/api/app/domain/services/eval_service.py` — capturar `IntegrityError` e retornar 409 com `existing_run_id`.
  - G-12: `apps/api/app/models.py:Plan` (`monthly_judge_budget_usd`), `apps/api/app/domain/services/eval_service.py`.
  - G-20: `apps/api/app/domain/services/usage_service.py` — `with_for_update()` no counter, somente em Postgres (skip em SQLite com warning).
  - G-25: `docker-compose.yml`, `apps/api/app/db.py`, secrets/env doc. Manter SQLite default em dev/test.
- **Mudanças esperadas**:
  - Plan ganha 3 campos. Plan free é seedado com limites razoáveis.
  - Ingest: após persistir, computar `spans_added` e `tokens_added`, chamar `enforce_usage_post(...)` que decide entre permitir overflow controlado OU rollback. Decisão recomendada: **rollback** se exceder >10% do limite.
  - Eval duplicada → 409 com `{"existing_run_id": "..."}`.
  - Judge budget consultado do Plan; default constante vira fallback.
  - `with_for_update()` em incremento. Test integ com 50 threads concorrentes não excede limite.
  - Postgres no `docker-compose.prod.yml`; SQLite continua em test/dev.
- **Mudanças proibidas**:
  - Reescrever schema de Plan (somente adicionar colunas).
  - Mudar contrato de 402 / 409.
- **Testes necessários**:
  - Integ: 1 trace com 1000 spans excede `monthly_span_limit=500` → 402.
  - Integ: 2 evals iguais em sequência → segundo 409 com `existing_run_id`.
  - Integ: budget de judge baixo (1 USD) esgota antes do default.
  - Integ (Postgres): 100 ingests concorrentes não excedem limite.
  - Smoke: docker-compose up com Postgres, criar org/key/trace, listar.
- **Comandos de validação**:
  - `pytest apps/api/tests -q`
  - Suite contra Postgres: `EVALOPS_DB_URL=postgresql+psycopg://... pytest apps/api/tests -q -k "quota or concurrency"`
- **Critérios de aceite**:
  - Todos os testes acima verdes em SQLite (skip de concurrency com warn) e em Postgres (full).
  - Docker compose de prod inicia com Postgres saudável.
- **Rollback strategy**:
  - Migração reversível (adicionar colunas → não destrutivo).
  - Postgres opt-in via env; revert para SQLite mantém compat.
- **O que fica para depois**:
  - Distribuir rate limit em Redis — Fase 7.
  - Worker assíncrono — fora.
  - Dump/backup automático de Postgres — fora.

---

### Fase 7 — Arquitetura e manutenção

- **Objetivo**: refatorar agora que regras estão corretas. Adicionar observabilidade e Alembic.
- **Gaps cobertos**: G-19, G-22, G-26, G-27, G-29, G-30 + extração de services + dedup de `_project_or_404`.
- **Prioridade**: P2/P3.
- **Risco**: Médio (refatoração ampla — testes precisam continuar verdes).
- **Dependências**: Fases 1–6 estáveis.
- **Arquivos prováveis**:
  - Extração: novos `apps/api/app/domain/services/{trace_ingest_service,export_service,api_key_service,experiment_service}.py` (este último consolida o que nasceu na Fase 3). Router fica fino.
  - `apps/api/app/deps.py` — novo `get_owned_project()` que substitui as 3 versões de `_project_or_404`.
  - `apps/api/alembic/` — bootstrap. Rev 0 = snapshot do schema atual.
  - `apps/api/app/main.py` — middleware de request_id.
  - Novo `apps/api/app/logging_config.py` — structlog ou logging stdlib com `JsonFormatter`.
  - `apps/api/app/models.py` — `ApiKey.expires_at` opcional.
  - `packages/sdk-python/evalops/uploader.py` — retry + dead-letter.
  - `apps/web/app/o/[org]/p/[project]/traces/page.tsx` — polling/SWR.
- **Mudanças esperadas**:
  - Router thin: parse → dep auth → call service → response. Sem queries SQL além de resolver ownership.
  - Helper único de project ownership.
  - Alembic operacional; CI roda `alembic upgrade head` em DB vazio.
  - Logs JSON com request_id, user_id, org_id, latency_ms.
  - SDK Python: retry 3× com jitter; dead-letter local em `~/.evalops/dead/`.
  - Frontend traces: auto-refresh leve (a cada 15s, parável).
- **Mudanças proibidas**:
  - Introduzir hexagonal completa, repositories abstratos, agregados DDD pesados.
  - Reescrever auth.
  - Mudar contratos OpenAPI sem aviso.
- **Testes necessários**:
  - Suíte existente verde após cada extração (suporte de regressão).
  - Smoke: `alembic upgrade head` em DB vazio recria schema completo.
  - Smoke: `GET /health/liveness` produz log JSON com request_id.
  - Unit SDK: mock 503 → 3 retries com backoff.
  - Integ: key expirada → 401.
- **Comandos de validação**:
  - `pytest apps/api/tests -q`
  - `pytest packages/sdk-python -q`
  - `pnpm --filter web typecheck && pnpm --filter web test`
  - `alembic upgrade head` em DB efêmero.
- **Critérios de aceite**:
  - Todas as suites verdes.
  - Routers críticos (`routes.py`, `routes_phase6.py`) com queries somente para resolver ownership.
  - Alembic adotado; `create_all` removido do lifespan (ou mantido só em test).
- **Rollback strategy**:
  - Cada extração em commit separado. Revert granular preservando testes.
  - Alembic atrás de env flag `EVALOPS_USE_ALEMBIC=1` durante transição.
- **O que fica para depois**:
  - OpenTelemetry / métricas Prometheus — fora do MVP.
  - 2FA — fora.
  - S3-backed exports — fora.

---

## 5. Matriz de dependências

| Gap | Depende de | Pode rodar paralelo a | Não misturar com | Risco de regressão | Exige E2E |
|---|---|---|---|---|---|
| G-02 | — | G-03, G-04 | G-14 (mesmo arquivo) | Médio (fluxo UI) | Sim |
| G-03 | — | G-02, G-04 | — | Baixo | Não |
| G-04 | — | G-02, G-03 | — | Baixo | Não (smoke build) |
| G-17 | — | G-02, G-03, G-04 | G-07 (mesmo arquivo) | Médio (rejeita payloads) | Não |
| G-01 | Fase 0 | G-13 | — | Médio (429 pode bloquear cliente legítimo) | Sim |
| G-13 | — | G-01 | G-16 | Baixo | Sim |
| G-15 | — | G-13, G-16 | — | Médio (sessões existentes) | Sim |
| G-16 | G-06 helper | G-13 | — | Baixo | Não |
| G-05 | Fase 0 | Fase 4 inteira | Fase 7 (mesmo arquivo após extração) | Alto (muda semântica) | Sim |
| G-06 | — | G-08, G-21 | — | Baixo | Não |
| G-08 | — | G-06, G-09 | G-17 (mesmo arquivo) | Médio (mudança em ingest) | Sim |
| G-09 | G-10 | G-06 | — | Baixo | Sim |
| G-10 | — | G-09 | — | Médio (arquivos existentes) | Não |
| G-21 | G-06 | G-08 | G-18 (mesmo list) | Médio (semântica DELETE) | Sim |
| G-14 | G-09 | G-18, G-23 | G-02 (mesmo arquivo) | Baixo | Sim |
| G-18 | — | G-14, G-23 | G-21 | Médio (consumidores ignoram cursor) | Sim |
| G-23 | — | G-14, G-18 | — | Baixo | Não |
| G-07 | G-06 | G-12 | G-17 | Médio (rejeita ingest) | Sim |
| G-11 | — | G-12 | — | Baixo | Não |
| G-12 | — | G-07, G-11 | — | Baixo | Não |
| G-20 | — | G-07 | — | Alto em Postgres, neutro em SQLite | Sim (carga) |
| G-25 | G-19 (preferível) | G-20 | — | Alto (storage de prod) | Sim |
| G-19 | Fases 1-6 estáveis | G-22 | — | Médio | Smoke |
| G-22 | — | G-19, G-26, G-27 | — | Baixo | Não |
| G-26 | — | G-22 | — | Baixo | Não |
| G-27 | — | G-22 | — | Baixo | Não |
| G-29 | G-18 | — | — | Baixo | Sim |

Regras derivadas:
- **G-02 e G-14 não misturar**: mesmo arquivo (`actions.ts` e `keys/page.tsx`) muda em ambas. Fazer G-02 na Fase 1, G-14 na Fase 5 — sem sobreposição temporal de PRs.
- **G-17 e G-08 não misturar**: ambas tocam ingest path; sequência G-17 → G-08 é mais segura.
- **G-21 e G-18 não misturar**: ambas tocam `list_traces`; fazer G-21 na Fase 4 e G-18 na Fase 5 não simultaneamente.
- **Alto risco de regressão (exigem revisão mais cuidadosa)**: G-05, G-20, G-25.
- **Paralelizáveis em PRs distintos**: dentro da Fase 2, G-01 e G-13 podem ir em paralelo. Fase 3 é totalmente independente das Fases 4 e 5 (escopo isolado).

---

## 6. Prompt de implementação por fase

> Cada prompt assume que `docs/audits/evalops-important-rules-audit.md` foi lido. Substituir `<FASE>` no copy/paste real.

### Prompt — Fase 0
```
Modelo: Sonnet (Medium effort)
Escopo permitido:
- Ler pyproject.toml, package.json, docker-compose, README.
- Rodar pytest, pnpm test/typecheck/build.
- Criar docs/plans/baseline.md.

Escopo proibido:
- Mudar qualquer arquivo de código produtivo.
- Adicionar deps, tocar configs.

Arquivos prováveis: docs/plans/baseline.md (novo).

Testes obrigatórios: rodar e registrar resultado da suíte atual.

Relatório final:
- Matriz de comandos descobertos.
- Lista de testes verdes / falhos.
- Tempo de execução por suíte.
- Falhas pré-existentes catalogadas.
```

### Prompt — Fase 1 (P0 segurança/configuração)
```
Modelo: Opus (High effort) — segurança crítica.
Escopo permitido:
- G-02: refatorar fluxo de criação de API key para não vazar key em URL.
- G-03: guard de fallback bearer em prod.
- G-04: throw em prod se base URL = localhost.
- G-17: middleware de payload size + cap de spans/trace.

Escopo proibido:
- Tocar audit log, rate limit, paginação, refactor de services.
- Mudar contrato de POST /v1/traces além de adicionar validação.

Arquivos prováveis:
- apps/web/lib/actions.ts, apps/web/lib/auth.ts, apps/web/lib/api.ts
- apps/web/app/o/[org]/p/[project]/keys/page.tsx
- apps/api/app/main.py, apps/api/app/api/routes.py

Testes obrigatórios:
- E2E web: criar key e validar ausência em URL/Referer.
- Unit web: hasFallbackToken em prod = false.
- Unit web: import em prod sem env throws.
- Integ API: payload > 8MB → 413; trace > 500 spans → 422.

Relatório final (formato):
1. Gaps fechados (G-XX).
2. Diff resumido por arquivo.
3. Testes adicionados.
4. Comandos de validação executados (com saída).
5. Riscos remanescentes / o que ficou para depois.
6. Rollback proposto.
```

### Prompt — Fase 2 (Rate limit e hardening de auth)
```
Modelo: Opus (Medium effort) — segurança + concorrência.
Escopo permitido:
- G-01: rate limit por API key (sliding window).
- G-13: rate limit em /login.
- G-15: POST /v1/auth/logout + denylist por jti.
- G-16: audit em failed_login.

Escopo proibido:
- Frontend (exceto se /logout exigir mudança trivial em actions).
- Mudar formato/claims de JWT além de adicionar jti.
- Refactor para multi-worker (Redis fica para Fase 7).

Arquivos prováveis:
- apps/api/app/deps.py
- apps/api/app/api/routes_auth.py
- apps/api/app/security.py
- apps/api/app/models.py (nova tabela RevokedToken; talvez ApiKeyUsageMinute)
- novo apps/api/app/domain/services/rate_limit_service.py

Testes obrigatórios:
- Integ: 61 calls/min → 429.
- Integ: 6 logins errados → 429.
- Integ: logout invalida JWT.
- Integ: 3 failed logins → 3 audit rows.

Relatório final: mesmo formato da Fase 1.
```

### Prompt — Fase 3 (Experiments reais)
```
Modelo: Opus (High effort) — lógica de domínio sensível, alto risco de regressão.
Escopo permitido:
- G-05: variants influenciam execução (prompt_version_ref, model).
- Criar apps/api/app/domain/services/experiment_service.py.
- Atualizar test_phase5 conforme necessário.

Escopo proibido:
- Worker assíncrono.
- Mudar formato de response (variants, comparisons, criteria_failures).
- Tocar UI além de smoke.

Arquivos prováveis:
- apps/api/app/api/routes_phase5.py
- novo apps/api/app/domain/services/experiment_service.py
- apps/api/app/schemas.py (extensão de ExperimentVariantIn se necessário)
- apps/api/tests/test_phase5_*.py

Testes obrigatórios:
- 2 variants distintas → scores distintos.
- 2 variants idênticas → scores iguais.
- Smoke: página /experiments renderiza.

Relatório final: mesmo formato + descrição clara de como variant resolve prompt/model.
```

### Prompt — Fase 4 (Audit log, privacy, exports)
```
Modelo: Sonnet (High effort) — alta cobertura, baixa complexidade individual.
Escopo permitido:
- G-06: audit em ações sensíveis (lista em docs/plans/evalops-remediation-roadmap.md).
- G-08: redaction opt-in via tags.pii=true ou header X-EvalOps-Redact.
- G-09: GET /v1/exports/{id}/download.
- G-10: EVALOPS_EXPORTS_DIR absoluto.
- G-21: soft delete de Trace + audit.

Escopo proibido:
- Cleanup automático de exports expirados.
- GET /v1/audit-logs (leitura).
- Hash/tokenization de user_ref.

Arquivos prováveis:
- helper de audit em apps/api/app/models.py ou apps/api/app/domain/services/audit_service.py
- apps/api/app/api/{routes.py,routes_phase5.py,routes_phase6.py,routes_evaluations.py,routes_rubrics.py}
- apps/api/app/domain/services/redaction_service.py (novo)
- apps/api/app/config.py (novo)
- apps/api/app/models.py (Trace.deleted_at)

Testes obrigatórios:
- Matriz: cada write listado → 1 audit row.
- Ingest com pii=true esconde messages no GET.
- Criar export → GET /download retorna JSONL.
- Export expirado → 410.
- DELETE trace → soft + audit.

Relatório final: mesmo formato.
```

### Prompt — Fase 5 (Contratos frontend↔backend, UX)
```
Modelo: Sonnet (Medium effort).
Escopo permitido:
- G-14: conectar ou marcar como "em breve" cada botão visível.
- G-18: cursor paginação real.
- G-23: whitelist de mensagens de erro.

Escopo proibido:
- Features novas de UI.
- Mudar layout além de conectar funcionalidade.
- Polling/SWR (Fase 7).

Arquivos prováveis:
- apps/web/app/o/[org]/p/[project]/traces/page.tsx (e demais páginas auditadas)
- apps/web/lib/actions.ts
- apps/web/lib/api.ts
- apps/api/app/api/routes.py (cursor em list_traces e demais)

Testes obrigatórios:
- E2E: cada botão visível tem handler ou data-status="planned".
- E2E: 250 traces, paginação 3 páginas.
- Unit web: error com SQL/stack → mensagem genérica.

Relatório final: mesmo formato.
```

### Prompt — Fase 6 (Robustez quota/eval/storage)
```
Modelo: Opus (High effort) — concorrência + storage de produção.
Escopo permitido:
- G-07: quota por spans/tokens.
- G-11: 409 em duplicate eval.
- G-12: judge budget por plano.
- G-20: lock pessimista no usage counter (Postgres only).
- G-25: docker-compose com Postgres para prod.

Escopo proibido:
- Worker assíncrono.
- Redis.
- Reescrever Plan schema (somente adicionar colunas).

Arquivos prováveis:
- apps/api/app/models.py (Plan)
- apps/api/app/domain/services/{usage_service.py,eval_service.py}
- apps/api/app/api/{routes.py,routes_evaluations.py}
- docker-compose.yml ou docker-compose.prod.yml
- apps/api/app/db.py

Testes obrigatórios:
- 1 trace com N spans excede span quota → 402.
- 2 evals iguais → 409.
- Budget baixo esgota.
- Concurrency (Postgres): 100 ingests concorrentes não excedem.
- Smoke Postgres.

Relatório final: mesmo formato + nota explícita sobre comportamento em SQLite vs Postgres.
```

### Prompt — Fase 7 (Arquitetura e manutenção)
```
Modelo: Sonnet (High effort) — refatoração ampla, suíte verde como rede de segurança.
Escopo permitido:
- Extrair 4 services (trace_ingest, export, api_key, experiment).
- Helper get_owned_project em deps.py.
- Adotar Alembic (G-19).
- Structured logging com request_id (G-22).
- G-26 ApiKey.expires_at.
- G-27 SDK retry.
- G-29 frontend auto-refresh.

Escopo proibido:
- Hexagonal, repositories abstratos, DDD pesado.
- Reescrever auth.
- Mudar contratos OpenAPI sem aviso.

Arquivos prováveis: múltiplos (ver Fase 7 detalhada).

Testes obrigatórios:
- Suíte existente verde após cada extração.
- alembic upgrade head em DB vazio.
- /health/liveness produz log JSON com request_id.
- SDK retry 3x.
- Key expirada → 401.

Relatório final: mesmo formato + tabela "linhas movidas por arquivo".
```

---

## 7. Recomendação de modelos

| Fase | Modelo | Effort | Justificativa |
|---|---|---|---|
| Fase 0 | Sonnet | Medium | Descoberta e documentação, sem decisão complexa. |
| Fase 1 (P0 segurança) | **Opus** | **High** | Segurança crítica, leak de secret, mudança de fluxo de UI. Custo justificado. |
| Fase 2 (rate limit/auth) | **Opus** | Medium | Concorrência + denylist; análise de bypass exige profundidade. |
| Fase 3 (experiments) | **Opus** | **High** | Regra de negócio errada hoje; refactor com risco alto de regressão. |
| Fase 4 (audit/privacy/exports) | Sonnet | High | Cobertura ampla, complexidade individual baixa; Sonnet alto effort cobre. |
| Fase 5 (contratos UX) | Sonnet | Medium | Frontend + paginação; mecânico. |
| Fase 6 (quota/eval/storage) | **Opus** | **High** | Postgres + concorrência + lock pessimista; falha silenciosa é cara. |
| Fase 7 (arquitetura) | Sonnet | High | Refactor amplo guiado por testes; Opus desnecessário se suíte robusta. |

Fatores de decisão aplicados:
- **Segurança crítica** → Opus High.
- **Concorrência/race** → Opus.
- **Cobertura ampla, mecânica** → Sonnet High.
- **Frontend mecânico** → Sonnet Medium.
- **Risco de regressão alto + mudança comportamental** → Opus High.
- **Custo**: Sonnet onde a suíte de teste dá segurança suficiente. Opus onde o modelo precisa pensar em adversário ou em invariante distribuída.

---

## 8. Ordem final recomendada

### Sequência ideal
1. **Fase 0** — baseline (1–2 dias).
2. **Fase 1** — P0 segurança/configuração (1 semana).
3. **Fase 2** — rate limit e auth hardening (1 semana).
4. **Fase 3** — experiments reais (3–5 dias).
5. **Fase 4** — audit log, privacy, exports (1–2 semanas).
6. **Fase 5** — contratos UX (1 semana).
7. **Fase 6** — robustez quota/eval/storage (1–2 semanas).
8. **Fase 7** — arquitetura e manutenção (2 semanas).

Total estimado: 8–11 semanas em ritmo sustentável.

### O que fazer primeiro
- Fase 0 sempre. Sem baseline confiável, qualquer afirmação de "está verde" é especulação.
- Em seguida, Fase 1 sem desvio. Os 4 gaps P0 dela são pré-requisito para qualquer demo externa ou onboarding pago.

### O que **não fazer agora**
- Não extrair services antes da Fase 7. Routers "feios" mas corretos > routers "limpos" mas com bugs.
- Não introduzir Redis, OpenTelemetry, S3, workers, 2FA, refresh token rotation. Tudo isso é após a Fase 7.
- Não reescrever Plan / Subscription / quota schema. Somente adicionar colunas.
- Não migrar de SQLite para Postgres em dev/test. Postgres é só prod (Fase 6).
- Não conectar polling automático no front antes de paginação real estar madura (Fase 5).

### Fases que podem ser implementadas por Codex/Sonnet
- **Fase 0**: Sonnet Medium é suficiente.
- **Fase 4**: Sonnet High, cobertura ampla e mecânica.
- **Fase 5**: Sonnet Medium, frontend + paginação.
- **Fase 7**: Sonnet High, refactor guiado por suíte verde.

### Fases que merecem Opus
- **Fase 1**: Opus High. Segurança crítica, leak ativo.
- **Fase 2**: Opus Medium. Rate limit, denylist, análise de bypass.
- **Fase 3**: Opus High. Lógica de domínio errada, risco de regressão alto.
- **Fase 6**: Opus High. Concorrência + storage de produção; falha cara.

### Regras de não-implementação cruzando fases
- **Não** transformar este MVP em arquitetura enterprise. Clean Architecture simplificada (router thin → service → model) é o teto.
- **Não** introduzir hexagonal/ports&adapters internamente — só para integração externa (LLM, S3, email) quando esses pontos aparecerem.
- **Não** criar repositories abstratos. Session SQLAlchemy direta dentro de service é suficiente até trocar para Postgres + métricas reais.
- **Não** inventar gaps não listados na auditoria, exceto quando dependência direta (ex: `EVALOPS_EXPORTS_DIR` é dependência de G-09).
- **Sim** documentar follow-ups em PR description quando descobertos durante implementação. Adicionar à próxima fase apropriada, nunca à atual.
