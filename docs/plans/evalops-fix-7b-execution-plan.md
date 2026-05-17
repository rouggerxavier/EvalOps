# Plano de Execução — Fix-7B Pós-Auditoria EvalOps

Data: 2026-05-15  
Branch de planejamento: `fix-7b`  
Fonte principal: `docs/audits/evalops-full-codebase-audit.md`  
Restrição desta etapa: planejamento apenas; nenhuma correção produtiva, teste, refactor, commit ou push.

## 1. Veredito da auditoria

Fix-7B existe porque a auditoria completa mostrou que o estado pós-Fases 1-6 e pós-7B tem features funcionais, mas ainda não tem consistência suficiente para deploy real. O problema central não é falta de novas features: é a divergência entre semântica de dados, UX, testes e deploy.

7C/7D/7E/7F ficam pausadas porque structured logging, SDK retry, key expiration, Redis e cleanup não reduzem o risco mais caro agora. Antes de continuar a Fase 7, o produto precisa fechar P0/P1 que podem expor dados soft-deletados, deixar sessão ativa após logout, aceitar quota além do plano, registrar custo/budget errado, falhar em gates por SQLite lock e subir produção sem migração Alembic.

Blockers P0/P1:

- A-01 P0: export inclui traces soft-deletados.
- A-02 P1: dashboard não chama `/v1/auth/logout`.
- A-03 P1: build de dataset usa traces soft-deletados.
- A-04 P1: evaluations por projeto listam runs de traces deletados.
- A-05 P1: idempotência de ingest com `client_trace_id` de trace deletado é ambígua.
- A-06 P1: quota check+increment não é atomicamente consistente.
- A-07 P1: commits parciais deixam dados sem usage/audit coerente.
- A-08 P1: `cost_cap_usd` é campo morto e budget de LLM judge é contornável.
- A-09 P1: suíte backend não é gate confiável por SQLite lock.
- A-10 P1: `npm audit` aponta Next/PostCSS vulneráveis.
- A-11 P1: `docker-compose.prod.yml` não executa Alembic apesar do código suportar.

Riscos de deploy:

- Dados logicamente removidos podem reaparecer em exports, datasets e listas de evaluations.
- Logout visual não revoga JWT no servidor.
- Testes falham por lock mesmo em blocos pequenos, então regressões podem passar sem prova confiável.
- Multi-worker/Postgres pode exceder quotas ou gerar race em `UsageCounter`.
- Judge budget não usa custo real e experiments com `llm_judge` podem contornar o gate.
- Erros internos podem vazar por API/UI.
- Produção pode subir com schema errado se Alembic não rodar antes do app.
- Web self-hosted permanece com advisories conhecidos até upgrade controlado.

## 2. Ordem recomendada das subfases

| Subfase | Prioridade | Motivo | Dependências | Modelo recomendado | Effort recomendado | Pode rodar em paralelo? | Bloqueia deploy? |
|---|---:|---|---|---|---|---|---|
| Fix-7B.3 — SQLite/test isolation | P1 | Sem gate confiável, toda correção posterior fica difícil de provar. | Nenhuma. Deve abrir a sequência. | Opus ou Codex high | High | Não; é habilitadora. | Sim, indiretamente |
| Fix-7B.1 — Soft delete consistency | P0/P1 | Fecha vazamento de dados soft-deletados em export/dataset/evaluations/idempotência. | Preferencialmente 7B.3 para teste confiável. | Opus ou Codex high | High | Depois de 7B.3, pode rodar em paralelo com 7B.2. | Sim |
| Fix-7B.2 — Logout real no frontend | P1 | Revoga JWT no servidor antes de limpar cookie local. | 7B.3 recomendada; backend logout já existe. | Sonnet/Codex medium | Medium | Sim, com 7B.1 se arquivos não colidirem. | Sim |
| Fix-7B.4 — Quota/concurrency transaction hardening | P1 | Une check+increment, trata race de counter e revisa commits parciais. | 7B.3; considerar impacto em 7B.1/7B.5. | Opus ou Codex high | High | Não recomendado; toca services centrais. | Sim |
| Fix-7B.5 — Judge budget e LLM cost consistency | P1 | Remove budget enganoso e fecha bypass de experiments com `llm_judge`. | 7B.4 recomendada, por uso/transação/custo. | Opus ou Codex high | High | Não recomendado; compartilha eval/experiment. | Sim para liberar LLM judge |
| Fix-7B.6 — Error sanitization + redaction hardening | P2 | Remove `str(exc)` público e amplia superfície PII. | 7B.1/7B.4/7B.5 para evitar conflito nos mesmos services. | Sonnet/Codex high | High | Parcial; frontend sanitization pode separar do backend. | Recomendado antes de deploy |
| Fix-7B.8 — Deploy/Alembic/npm audit | P1 | Alinha compose com Alembic e planeja upgrade controlado de Next/PostCSS. | 7B.3 para gates; pode anteceder 7B.6/7B.7. | Opus/Codex high para deploy, Sonnet high para web upgrade | High | Parcial: Alembic/compose e npm podem ser PRs separados. | Sim |
| Fix-7B.7 — Frontend contract/UX cleanup | P2 | Conecta download de export, remove botões órfãos e atualiza usage types. | 7B.2 e 7B.6 recomendadas para auth/errors. | Sonnet/Codex medium | Medium | Sim, se 7B.8 web upgrade não estiver mexendo nos mesmos arquivos. | Não, mas afeta confiança |
| Fix-7B.9 — SDK reliability | P2 | Evita perda silenciosa de telemetria no SDK. | Nenhuma; ideal depois dos P1. | Sonnet/Codex medium | Medium | Sim; escopo isolado em `packages/sdk-python`. | Não para backend/web, sim para SDK externo |

Ordem prática recomendada:

1. Fix-7B.3.
2. Fix-7B.1.
3. Fix-7B.2.
4. Fix-7B.4.
5. Fix-7B.5.
6. Fix-7B.8.
7. Fix-7B.6.
8. Fix-7B.7.
9. Fix-7B.9.

Se houver urgência de privacidade acima da confiabilidade do gate, Fix-7B.1 pode ser executada antes de Fix-7B.3 com validação isolada manual. A recomendação padrão ainda é estabilizar o gate primeiro.

## 3. Mapa de achados da auditoria

| ID da auditoria | Prioridade | Categoria | Subfase responsável | Arquivos prováveis | Teste esperado | Status atual |
|---|---:|---|---|---|---|---|
| A-01 | P0 | Dados/privacidade | Fix-7B.1 | `apps/api/app/domain/services/export_service.py`, `apps/api/tests/test_phase10_audit_privacy_exports.py` | Export JSONL não contém `Trace.deleted_at IS NOT NULL`. | Aberto: `_filter_traces` filtra só `project_id`. |
| A-02 | P1 | Segurança/auth | Fix-7B.2 | `apps/web/lib/auth-actions.ts`, `apps/web/lib/auth.ts`, `apps/web/lib/api.ts`, `apps/web/tests/`, `apps/api/tests/test_phase9_auth_hardening.py` | Logout do dashboard chama backend e token revogado retorna 401. | Aberto: `logoutAction()` só limpa cookie. |
| A-03 | P1 | Dados/soft delete | Fix-7B.1 | `apps/api/app/api/routes_phase5.py`, `apps/api/tests/test_phase5_prompts_datasets_experiments.py` | `build-from-traces` ignora traces deletados. | Aberto: query não filtra `Trace.deleted_at`. |
| A-04 | P1 | Dados/soft delete | Fix-7B.1 | `apps/api/app/api/routes_evaluations.py`, `apps/api/tests/test_phase4_rubrics_eval.py` ou `test_phase10_audit_privacy_exports.py` | Lista por projeto não retorna runs cujo trace foi deletado. | Aberto: join com `Trace` sem filtro de deleted. |
| A-05 | P1 | Dados/idempotência | Fix-7B.1 | `apps/api/app/domain/services/trace_ingest_service.py`, `apps/api/tests/test_phase10_audit_privacy_exports.py` | Contrato para `client_trace_id` de trace deletado é explícito e testado. | Aberto: `_existing_trace_id` não diferencia deleted. |
| A-06 | P1 | Quota/concurrency | Fix-7B.4 | `apps/api/app/domain/services/usage_service.py`, `apps/api/tests/test_phase12_quota_eval_storage.py` | Check+increment é atômico em Postgres; race de criação é tratada. | Aberto: `enforce_quota` e `increment_usage` separados. |
| A-07 | P1 | Consistência transacional | Fix-7B.4 | `trace_ingest_service.py`, `routes_evaluations.py`, `export_service.py` | Falha em usage/audit não deixa registro principal incoerente sem contrato. | Aberto: commits parciais em ingest/eval/export. |
| A-08 | P1 | Budget/custos | Fix-7B.5 | `llm_judge.py`, `eval_service.py`, `experiment_service.py`, `routes_evaluations.py` | `cost_cap_usd` tem efeito real ou é removido do contrato; experiments respeitam budget. | Aberto: custo LLM não é registrado; experiments contornam pre-check. |
| A-09 | P1 | Testabilidade | Fix-7B.3 | `apps/api/tests/`, `apps/api/app/db.py`, `apps/api/app/main.py` | Phase8/9/10 e regressão rodam sem SQLite lock. | Aberto: fixtures usam DB compartilhado/drop_all por arquivo. |
| A-10 | P1 | Dependências | Fix-7B.8 | `apps/web/package.json`, lockfile, web tests/build | Next/PostCSS fora dos advisories com `tsc`, build e tests verdes. | Aberto: Next 15.3.9 e PostCSS vulneráveis no audit. |
| A-11 | P1 | Deploy/migração | Fix-7B.8 | `docker-compose.prod.yml`, `.env.example`, `README.md`, `docs/ops/database-migrations.md` | Compose/ops executa `alembic upgrade head` antes do app. | Aberto: compose diz que Alembic não foi adotado. |
| A-12 | P2 | Segurança/erros | Fix-7B.6 | `trace_ingest_service.py`, `export_service.py`, `eval_service.py`, `routes_phase5.py`, `routes_rubrics.py`, `apps/web/lib/api.ts`, error pages | Respostas públicas e UI não exibem `str(exc)`, SQL, paths ou stack. | Aberto: várias rotas/services persistem ou exibem erro bruto. |
| A-13 | P2 | Redaction/PII | Fix-7B.6 | `redaction_service.py`, `trace_ingest_service.py`, schemas/tests | Redaction opt-in cobre events, tags, metadata, user_ref e errors conforme contrato. | Aberto: só `messages_in/out`, `input/output` são limpos. |
| A-14 | P2 | Auth/rate limit | Follow-up fora Fix-7B mínimo ou 7B.6/8 se proxy for tocado | `routes_auth.py`, `deps.py`, deploy docs | Trusted proxy e debounce de `last_used_at` documentados/testados. | Aberto; não é subfase principal. |
| A-15 | P2 | API key lifecycle | Pós-MVP/7E | `api_key_service.py`, `models.ApiKey`, Alembic | Expiração/scopes validados por contrato. | Aberto; não entra no Fix-7B salvo documentação de não escopo. |
| A-16 | P2 | Frontend contrato/UX | Fix-7B.7 | `apps/web/app/o/[org]/p/[project]/exports/page.tsx`, `apps/web/lib/api.ts`, `apps/web/lib/types.ts` | UI mostra download autenticado para export completed. | Aberto: UI copia path e desabilita download. |
| A-17 | P2 | SDK confiabilidade | Fix-7B.9 | `packages/sdk-python/evalops/uploader.py`, `packages/sdk-python/tests/test_sdk.py`, SDK README | Retry/backoff, não-2xx e queue full têm comportamento documentado/testado. | Aberto: perdas silenciosas. |
| A-18 | P2 | Arquitetura | Não prioritário no Fix-7B | `routes_phase5.py`, `eval_service.py`, `experiment_service.py` | Refactors só se necessários para bugs P0/P1. | Aberto; não criar DDD pesado. |

## 4. Subfases detalhadas

### Fix-7B.1 — Soft delete consistency

- Objetivo: garantir que `Trace.deleted_at` seja respeitado em export, build de dataset, listagem de evaluations por projeto e idempotência de ingest.
- Achados cobertos: A-01, A-03, A-04, A-05.
- Escopo permitido: filtros de query em services/routers existentes; contrato explícito para reingest de `client_trace_id` deletado; testes focados.
- Escopo proibido: hard delete/purge físico, endpoints admin de `include_deleted`, refactor amplo de `routes_phase5.py`, alteração de schemas públicos sem necessidade.
- Arquivos prováveis: `apps/api/app/domain/services/export_service.py`, `apps/api/app/domain/services/trace_ingest_service.py`, `apps/api/app/api/routes_phase5.py`, `apps/api/app/api/routes_evaluations.py`, `apps/api/tests/test_phase10_audit_privacy_exports.py`, `apps/api/tests/test_phase5_prompts_datasets_experiments.py`, `apps/api/tests/test_phase4_rubrics_eval.py`.
- Comportamento esperado: queries operacionais ignoram traces deletados; export row_count reflete só traces ativos; datasets não criam items de traces deletados; project evaluations não listam runs de traces deletados; reingest de `client_trace_id` deletado segue contrato único.
- Contrato recomendado para idempotência: não reutilizar ID morto; retornar 409 estruturado `{"error":"trace_deleted","client_trace_id":...}` até haver restore explícito. Alternativa aceitável: ignorar deleted e criar novo trace somente se o unique constraint for ajustado em Postgres com índice parcial, o que exige migration e é mais arriscado.
- Testes obrigatórios: export exclui deleted; dataset build exclui deleted; evaluations por projeto excluem deleted; reingest de deleted retorna o contrato escolhido; regressão de ingest idempotente para trace ativo continua verde.
- Comandos de validação: `cd apps/api && python -m pytest tests/test_phase10_audit_privacy_exports.py tests/test_phase5_prompts_datasets_experiments.py tests/test_phase4_rubrics_eval.py -q --tb=short -p no:warnings`.
- Critérios de aceite: todos os achados A-01/A-03/A-04/A-05 têm teste vermelho antes/verde depois; nenhum endpoint passa a retornar trace deletado em fluxo normal; contrato documentado no teste e, se necessário, em doc operacional.
- Riscos: mudança observável para clientes que dependiam de runs antigos; unique constraint `(project_id, client_trace_id)` limita recriação sem migration.
- Rollback: revert do PR; nenhum schema se o contrato 409 for adotado.
- Modelo recomendado: Opus ou Codex high.
- Effort recomendado: High.
- Prompt pronto para execução:

```text
Contexto:
Você está no EvalOps na fase Fix-7B.1. A auditoria `docs/audits/evalops-full-codebase-audit.md` apontou A-01 P0, A-03 P1, A-04 P1 e A-05 P1 sobre inconsistência de soft delete. Não implemente outras subfases.

Arquivos relevantes:
- apps/api/app/domain/services/export_service.py
- apps/api/app/domain/services/trace_ingest_service.py
- apps/api/app/api/routes_phase5.py
- apps/api/app/api/routes_evaluations.py
- apps/api/app/models.py
- apps/api/tests/test_phase10_audit_privacy_exports.py
- apps/api/tests/test_phase5_prompts_datasets_experiments.py
- apps/api/tests/test_phase4_rubrics_eval.py

Escopo permitido:
- Adicionar filtros `Trace.deleted_at.is_(None)` nos caminhos operacionais de export, dataset build e project evaluations.
- Definir e implementar contrato explícito para ingest idempotente quando `client_trace_id` pertence a trace soft-deletado; recomendação: 409 `trace_deleted`, sem recriar registro.
- Adicionar testes focados para cada bug.

Escopo proibido:
- Não fazer hard delete/purge.
- Não criar endpoint admin `include_deleted`.
- Não refatorar routers por estética.
- Não alterar frontend, SDK, Docker ou npm.
- Não misturar quota, LLM budget ou sanitização de erro.

Testes:
- Export não inclui trace deletado.
- Build de dataset não cria item a partir de trace deletado.
- `GET /projects/{project_id}/evaluations` não lista run de trace deletado.
- Reingest com `client_trace_id` deletado segue contrato testado.
- Idempotência de trace ativo continua retornando o mesmo trace_id.

Comandos:
- cd apps/api && python -m pytest tests/test_phase10_audit_privacy_exports.py tests/test_phase5_prompts_datasets_experiments.py tests/test_phase4_rubrics_eval.py -q --tb=short -p no:warnings
- cd apps/api && python -m pytest tests/test_phase8_p0_security.py -q --tb=short -p no:warnings

Documentação:
- Atualize somente documentação mínima se o contrato de reingest precisar ser registrado.
- Não edite este plano salvo para marcar status depois da execução.

Relatório final esperado:
- Lista de arquivos alterados.
- Contrato escolhido para `client_trace_id` deletado.
- Testes adicionados/alterados.
- Comandos executados e resultado.
- Confirmação de que nenhuma outra subfase foi implementada.
```

### Fix-7B.2 — Logout real no frontend

- Objetivo: fazer o logout do dashboard revogar o JWT no backend antes de limpar cookie/sessão local.
- Achados cobertos: A-02.
- Escopo permitido: server action de logout, helper API para `POST /v1/auth/logout`, testes web/backend que comprovem revogação.
- Escopo proibido: refresh tokens, 2FA, redesign de auth, alteração de `routes_auth.py` salvo teste ou bug mínimo comprovado.
- Arquivos prováveis: `apps/web/lib/auth-actions.ts`, `apps/web/lib/auth.ts`, `apps/web/lib/api.ts`, `apps/web/tests/security.test.mjs`, `apps/api/tests/test_phase9_auth_hardening.py`.
- Comportamento esperado: logout com sessão chama backend com bearer atual; se backend falha, cookie local ainda é limpo; token revogado não acessa endpoints protegidos; logout permanece idempotente.
- Testes obrigatórios: teste web mockando fetch para garantir chamada a `/v1/auth/logout`; teste backend existente ou novo comprovando token revogado; teste de fallback quando não há token.
- Comandos de validação: `cd apps/web && npm run test && npx tsc --noEmit && npm run build`; `cd apps/api && python -m pytest tests/test_phase9_auth_hardening.py -q --tb=short -p no:warnings`.
- Critérios de aceite: logout real acionado pelo dashboard; cookie limpo mesmo se revoke não responder; nenhuma exposição de token em URL/log.
- Riscos: server action precisa obter token antes de limpar cookie; falha de rede durante logout pode deixar token válido no servidor, mas a UI local deve sair.
- Rollback: revert do patch frontend; backend já suporta logout.
- Modelo recomendado: Sonnet/Codex medium.
- Effort recomendado: Medium.
- Prompt pronto para execução:

```text
Contexto:
Você está no EvalOps na fase Fix-7B.2. A auditoria apontou A-02 P1: o backend tem `POST /v1/auth/logout`, mas `apps/web/lib/auth-actions.ts::logoutAction()` só limpa cookie. Corrija apenas o logout real.

Arquivos relevantes:
- apps/web/lib/auth-actions.ts
- apps/web/lib/auth.ts
- apps/web/lib/api.ts
- apps/web/tests/security.test.mjs
- apps/api/app/api/routes_auth.py
- apps/api/tests/test_phase9_auth_hardening.py

Escopo permitido:
- Criar helper web para chamar `POST /v1/auth/logout` com o bearer atual.
- Alterar `logoutAction()` para tentar revoke no servidor antes de limpar cookie.
- Garantir que cookie/sessão local seja limpo mesmo se o revoke falhar.
- Adicionar/ajustar testes web e, se necessário, backend.

Escopo proibido:
- Não redesenhar auth.
- Não criar refresh token, 2FA, nova sessão ou nova tabela.
- Não mexer em soft delete, quota, SDK, Docker ou npm.
- Não alterar contratos de login/register.

Testes:
- Web: logout action chama `/v1/auth/logout` com Authorization.
- Web: logout sem token ainda limpa sessão local.
- Backend: token revogado não autentica depois de logout.

Comandos:
- cd apps/web && npm run test
- cd apps/web && npx tsc --noEmit
- cd apps/web && npm run build
- cd apps/api && python -m pytest tests/test_phase9_auth_hardening.py -q --tb=short -p no:warnings

Documentação:
- Só atualizar docs se o fluxo de logout documentado estiver errado.

Use a skill/ferramenta UI UX Pro Max para apoiar decisões de design, hierarquia visual, usabilidade, acessibilidade, consistência de componentes e estados de interface.

Relatório final esperado:
- Lista de arquivos alterados.
- Descrição do fluxo de logout em sucesso e falha de rede.
- Testes executados e resultado.
- Confirmação de que nenhum outro hardening foi misturado.
```

### Fix-7B.3 — SQLite/test isolation

- Objetivo: tornar os testes backend um gate confiável, eliminando ou mitigando `sqlite3.OperationalError: database is locked` nos arquivos Phase8/9/10 e regressões.
- Achados cobertos: A-09.
- Escopo permitido: fixtures de teste, override de DB por teste/processo, encerramento de sessions/clients, configuração de engine test-only.
- Escopo proibido: alterar comportamento produtivo, migrar dev/test obrigatoriamente para Postgres, mudar asserts para esconder bug, remover testes lentos sem substituição.
- Arquivos prováveis: `apps/api/tests/`, possível `apps/api/tests/conftest.py`, `apps/api/app/db.py` somente se necessário com caminho test-only seguro, `apps/api/app/main.py` se lifespan precisar de isolamento test-only.
- Comportamento esperado: cada teste ou arquivo usa DB temporário isolado; `TestClient` fecha lifespan; sessions são encerradas; `drop_all/create_all` não disputa conexão aberta.
- Testes obrigatórios: Phase8, Phase9, Phase10, Phase12 e um grupo de regressão legado rodam em sequência no mesmo comando; se houver paralelismo, cada worker usa DB próprio.
- Comandos de validação: `cd apps/api && python -m pytest tests/test_phase8_p0_security.py tests/test_phase9_auth_hardening.py tests/test_phase10_audit_privacy_exports.py tests/test_phase12_quota_eval_storage.py -q --tb=short -p no:warnings`; depois grupo legado documentado.
- Critérios de aceite: zero SQLite lock nas suítes alvo; fixtures reaproveitáveis; testes não dependem de `rm -f evalops.db*` manual.
- Riscos: mexer em fixtures pode mascarar diferenças entre app real e app test; uso de in-memory SQLite com múltiplas conexões pode perder schema se pool errado.
- Rollback: revert das fixtures e voltar ao workaround por arquivo.
- Modelo recomendado: Opus ou Codex high.
- Effort recomendado: High.
- Prompt pronto para execução:

```text
Contexto:
Você está no EvalOps na fase Fix-7B.3. A auditoria apontou A-09 P1: os testes backend Phase8/9/10 falham por SQLite lock, então o gate de regressão não é confiável. Corrija isolamento de testes, não comportamento produtivo.

Arquivos relevantes:
- apps/api/tests/
- apps/api/app/db.py
- apps/api/app/main.py
- apps/api/tests/test_phase8_p0_security.py
- apps/api/tests/test_phase9_auth_hardening.py
- apps/api/tests/test_phase10_audit_privacy_exports.py
- apps/api/tests/test_phase12_quota_eval_storage.py

Escopo permitido:
- Criar `apps/api/tests/conftest.py` com fixture de DB temporário por teste ou por worker.
- Override limpo de `get_db`.
- Garantir `TestClient` como context manager quando necessário.
- Fechar sessions e limpar `app.dependency_overrides`.
- Ajustar testes existentes só para usar fixture comum, sem reduzir cobertura.

Escopo proibido:
- Não alterar código produtivo salvo pequeno suporte test-only claramente isolado.
- Não migrar a suíte para Postgres obrigatório.
- Não apagar asserts ou pular testes por lock.
- Não implementar fixes de soft delete/quota/logout junto.

Testes:
- Phase8, Phase9, Phase10 e Phase12 rodam no mesmo processo sem lock.
- Grupo legado health/auth/phase1/phase2/phase3/phase6/phase7 roda sem lock.
- Testes que dependem de lifespan continuam criando schema.

Comandos:
- cd apps/api && python -m pytest tests/test_phase8_p0_security.py tests/test_phase9_auth_hardening.py tests/test_phase10_audit_privacy_exports.py tests/test_phase12_quota_eval_storage.py -q --tb=short -p no:warnings
- cd apps/api && python -m pytest tests/test_health.py tests/test_auth_flow.py tests/test_phase1_identity_access.py tests/test_phase2_tracing.py tests/test_phase3_analytics.py tests/test_phase6_feedback_export_usage.py tests/test_phase7_e2e_mvp_flow.py -q --tb=short -p no:warnings
- cd apps/api && python -m pytest tests -q --tb=short -p no:warnings

Documentação:
- Atualize `docs/plans/baseline.md` somente se a equipe quiser registrar que o workaround `rm -f evalops.db*` deixou de ser obrigatório.

Relatório final esperado:
- Estratégia escolhida de isolamento.
- Arquivos de teste alterados.
- Comandos executados e resultado.
- Qualquer limitação remanescente de SQLite.
```

### Fix-7B.4 — Quota/concurrency transaction hardening

- Objetivo: tornar quota e usage consistentes em transação, sem race na criação de `UsageCounter` e sem commits parciais em ingest/evaluation/export.
- Achados cobertos: A-06, A-07.
- Escopo permitido: API interna de `usage_service`, transações por use case, tratamento de `IntegrityError` em counter, testes de concorrência onde viável.
- Escopo proibido: Redis/distributed lock, worker assíncrono, billing real, refactor arquitetural amplo, alterar planos/limites públicos sem necessidade.
- Arquivos prováveis: `apps/api/app/domain/services/usage_service.py`, `trace_ingest_service.py`, `export_service.py`, `eval_service.py`, `apps/api/app/api/routes_evaluations.py`, `apps/api/tests/test_phase12_quota_eval_storage.py`.
- Comportamento esperado: check+increment executa com lock no mesmo fluxo; se dois workers criarem counter, um recupera a linha existente; falha de usage/audit não deixa registro principal como sucesso sem contrato explícito.
- Testes obrigatórios: quota no limite em requisições concorrentes; race de criação de `UsageCounter`; falha simulada de increment/audit em ingest/evaluation/export tem rollback ou status de erro documentado.
- Comandos de validação: `cd apps/api && python -m pytest tests/test_phase12_quota_eval_storage.py tests/test_phase8_p0_security.py tests/test_phase10_audit_privacy_exports.py -q --tb=short -p no:warnings`.
- Critérios de aceite: não há caminho normal com `enforce_quota()` separado de `increment_usage()` sem justificativa; Postgres usa `FOR UPDATE` onde aplicável; SQLite mantém comportamento testável.
- Riscos: alterar fronteiras de commit pode mudar timing de IDs e audit; Postgres e SQLite têm semânticas diferentes de lock.
- Rollback: revert do PR; sem migration se API interna for mantida.
- Modelo recomendado: Opus ou Codex high.
- Effort recomendado: High.
- Prompt pronto para execução:

```text
Contexto:
Você está no EvalOps na fase Fix-7B.4. A auditoria apontou A-06 P1 e A-07 P1: quota check+increment não é atômico, criação concorrente de `UsageCounter` tem race e ingest/evaluation/export fazem commits parciais. Corrija hardening transacional sem criar infraestrutura nova.

Arquivos relevantes:
- apps/api/app/domain/services/usage_service.py
- apps/api/app/domain/services/trace_ingest_service.py
- apps/api/app/domain/services/export_service.py
- apps/api/app/domain/services/eval_service.py
- apps/api/app/api/routes_evaluations.py
- apps/api/app/models.py
- apps/api/tests/test_phase12_quota_eval_storage.py

Escopo permitido:
- Criar função de usage que faça check+increment dentro da mesma transação.
- Usar `with_for_update()` em Postgres para row existente.
- Tratar `IntegrityError` ao criar `UsageCounter` e recarregar linha.
- Revisar commits parciais de ingest/evaluation/export com testes.

Escopo proibido:
- Não introduzir Redis, Celery, outbox completa ou billing provider.
- Não mudar limites de planos.
- Não mexer em UI, SDK, npm ou Docker.
- Não implementar judge budget real além do necessário para manter testes verdes; isso é Fix-7B.5.

Testes:
- Exceder quota no limite retorna 402 e não incrementa.
- Concorrência de criação de counter não estoura 500.
- Ingest/evaluation/export não deixam sucesso parcial quando usage falha.
- Regressão de Phase12 continua verde.

Comandos:
- cd apps/api && python -m pytest tests/test_phase12_quota_eval_storage.py -q --tb=short -p no:warnings
- cd apps/api && python -m pytest tests/test_phase8_p0_security.py tests/test_phase10_audit_privacy_exports.py tests/test_phase4_rubrics_eval.py -q --tb=short -p no:warnings

Documentação:
- Documente em comentário curto ou doc operacional a diferença SQLite vs Postgres se continuar relevante.

Relatório final esperado:
- Nova API interna de usage.
- Lista de fluxos revisados e decisão transacional de cada um.
- Testes executados e resultado.
- Risco residual em SQLite/Postgres.
```

### Fix-7B.5 — Judge budget e LLM cost consistency

- Objetivo: garantir que budget de judge e custos LLM sejam reais ou tenham contrato explícito que não engane o usuário.
- Achados cobertos: A-08.
- Escopo permitido: uso real de `cost_cap_usd`, estimativa/registro de custo de `llm_judge`, gate para experiments, testes com LLM mockado.
- Escopo proibido: integração ampla com billing externo, chamadas LLM reais em teste, worker assíncrono, redesign de rubrics.
- Arquivos prováveis: `apps/api/app/domain/evaluators/llm_judge.py`, `apps/api/app/domain/services/eval_service.py`, `apps/api/app/domain/services/experiment_service.py`, `apps/api/app/api/routes_evaluations.py`, `apps/api/tests/test_phase4_rubrics_eval.py`, `apps/api/tests/test_phase5_prompts_datasets_experiments.py`, `apps/api/tests/test_phase12_quota_eval_storage.py`.
- Comportamento esperado: `cost_cap_usd` limita execução ou é removido/renomeado; cada LLM judge registra custo estimado/real; experiments com `llm_judge` usam o mesmo budget gate; budget não é contornado por rota alternativa.
- Testes obrigatórios: `cost_cap_usd` bloqueia/limita chamada com custo estimado; run de evaluation soma custo; experiment com `llm_judge` e budget esgotado falha de forma estruturada; evaluator sem LLM não usa budget.
- Comandos de validação: `cd apps/api && python -m pytest tests/test_phase4_rubrics_eval.py tests/test_phase5_prompts_datasets_experiments.py tests/test_phase12_quota_eval_storage.py -q --tb=short -p no:warnings`.
- Critérios de aceite: campo `cost_cap_usd` não é morto; budget status reflete custo registrado; nenhum caminho de `llm_judge` roda sem gate.
- Riscos: custo real pode não estar disponível na API mockada; estimativa por token precisa ser conservadora e documentada.
- Rollback: revert do PR; sem migration esperada.
- Modelo recomendado: Opus ou Codex high.
- Effort recomendado: High.
- Prompt pronto para execução:

```text
Contexto:
Você está no EvalOps na fase Fix-7B.5. A auditoria apontou A-08 P1: `llm_judge.cost_cap_usd` é campo morto, budget soma `EvaluationRun.cost_usd`, mas LLM judge não registra custo real e experiments podem contornar o gate. Corrija apenas budget/custo de judge.

Arquivos relevantes:
- apps/api/app/domain/evaluators/llm_judge.py
- apps/api/app/domain/services/eval_service.py
- apps/api/app/domain/services/experiment_service.py
- apps/api/app/api/routes_evaluations.py
- apps/api/app/infra/llm/pricing.py
- apps/api/tests/test_phase4_rubrics_eval.py
- apps/api/tests/test_phase5_prompts_datasets_experiments.py
- apps/api/tests/test_phase12_quota_eval_storage.py

Escopo permitido:
- Fazer `cost_cap_usd` ter efeito real ou explicitar novo contrato sem campo morto.
- Estimar/registrar custo para LLM judge com testes mockados.
- Aplicar gate de judge budget em experiments que usam rubrics com `llm_judge`.
- Retornar erro estruturado quando budget/cap bloquear execução.

Escopo proibido:
- Não chamar LLM real em testes.
- Não implementar billing externo.
- Não criar worker assíncrono.
- Não mexer em frontend, SDK, Docker ou npm.

Testes:
- LLM judge com custo estimado acima de `cost_cap_usd` não executa ou retorna erro controlado.
- Evaluation com LLM judge registra `cost_usd` no score/run.
- Budget esgotado bloqueia evaluation e experiment.
- Rubric sem LLM judge não é bloqueada por budget.

Comandos:
- cd apps/api && python -m pytest tests/test_phase4_rubrics_eval.py tests/test_phase5_prompts_datasets_experiments.py tests/test_phase12_quota_eval_storage.py -q --tb=short -p no:warnings

Documentação:
- Atualize doc mínima do contrato de `cost_cap_usd` se o comportamento público mudar.

Relatório final esperado:
- Decisão sobre custo real vs estimado.
- Como `cost_cap_usd` é aplicado.
- Como experiments foram protegidos.
- Testes executados e resultado.
```

### Fix-7B.6 — Error sanitization + redaction hardening

- Objetivo: separar erro interno de resposta pública e ampliar redaction opt-in para a superfície PII documentada.
- Achados cobertos: A-12, A-13.
- Escopo permitido: helper de sanitização backend; substituição de `str(exc)` público; sanitização de page-level errors no frontend; redaction recursiva em campos sensíveis.
- Escopo proibido: nova política automática de DLP/PII por ML, criptografia/tokenização de `user_ref`, alteração de payload bruto sem opt-in, grande redesign de UI.
- Arquivos prováveis: `trace_ingest_service.py`, `export_service.py`, `eval_service.py`, `routes_phase5.py`, `routes_rubrics.py`, `redaction_service.py`, `apps/web/lib/api.ts`, `apps/web/lib/actions.ts`, error pages e pages de keys/datasets/exports.
- Comportamento esperado: API retorna slugs/erros seguros; detalhes internos ficam em logs/audit internos quando necessário; UI page-level não imprime SQL/path/stack; redaction opt-in cobre messages, input/output, event payload, trace tags, trace metadata, span metadata, span error e user_ref conforme contrato.
- Testes obrigatórios: exceções simuladas não vazam SQL/stack/path; redaction remove PII dos campos ampliados; campos não sensíveis preservam estrutura suficiente; frontend sanitiza `error.message` em error boundaries/pages.
- Comandos de validação: backend Phase8/10/12 e frontend tests/tsc/build.
- Critérios de aceite: `rg "str\\(exc\\)"` não encontra uso em resposta pública sem justificativa; redaction tem teste de matriz; UI mostra mensagem genérica acionável.
- Riscos: redaction pode remover dados úteis para debug; manter raw interno requer cuidado para não expor via schema.
- Rollback: revert do PR; atenção a testes de contrato se redaction mudar payload.
- Modelo recomendado: Sonnet/Codex high.
- Effort recomendado: High.
- Prompt pronto para execução:

```text
Contexto:
Você está no EvalOps na fase Fix-7B.6. A auditoria apontou A-12 P2 e A-13 P2: `str(exc)` vaza em respostas/armazenamento público e redaction opt-in não cobre toda a superfície PII. Corrija sanitização e redaction sem mudar features.

Arquivos relevantes:
- apps/api/app/domain/services/trace_ingest_service.py
- apps/api/app/domain/services/export_service.py
- apps/api/app/domain/services/eval_service.py
- apps/api/app/domain/services/redaction_service.py
- apps/api/app/api/routes_phase5.py
- apps/api/app/api/routes_rubrics.py
- apps/web/lib/api.ts
- apps/web/lib/actions.ts
- apps/web/app/o/[org]/p/[project]/**/error.tsx
- apps/web/app/o/[org]/p/[project]/**/page.tsx
- apps/api/tests/test_phase8_p0_security.py
- apps/api/tests/test_phase10_audit_privacy_exports.py
- apps/api/tests/test_phase12_quota_eval_storage.py
- apps/web/tests/security.test.mjs

Escopo permitido:
- Criar helper backend para erro público seguro.
- Trocar respostas públicas com `str(exc)` por slugs ou mensagens seguras.
- Manter detalhes internos apenas em logs/audit internos, se existirem.
- Ampliar redaction opt-in para event payload, tags, metadata, user_ref e errors.
- Sanitizar page-level errors no frontend.

Escopo proibido:
- Não criar DLP automático pesado.
- Não criptografar/tokenizar dados.
- Não alterar UX além de mensagens de erro seguras.
- Não mexer em quota, logout, Docker, npm ou SDK.

Testes:
- Erro com SQLAlchemy/SQLite/path/stack não aparece em resposta pública.
- Redaction opt-in limpa todos os campos documentados.
- Frontend error pages não exibem `error.message` bruto.
- Regressão de server actions sanitizadas continua verde.

Comandos:
- cd apps/api && python -m pytest tests/test_phase8_p0_security.py tests/test_phase10_audit_privacy_exports.py tests/test_phase12_quota_eval_storage.py -q --tb=short -p no:warnings
- cd apps/web && npm run test
- cd apps/web && npx tsc --noEmit
- cd apps/web && npm run build

Documentação:
- Documente a superfície redigida opt-in em doc ou comentário próximo do serviço.

Use a skill/ferramenta UI UX Pro Max para apoiar decisões de design, hierarquia visual, usabilidade, acessibilidade, consistência de componentes e estados de interface.

Relatório final esperado:
- Lista de pontos `str(exc)` removidos ou justificados.
- Matriz de campos redigidos.
- Testes executados e resultado.
- Riscos residuais de PII.
```

### Fix-7B.7 — Frontend contract/UX cleanup

- Objetivo: alinhar UI aos contratos reais de backend e remover controles enganosos.
- Achados cobertos: A-16 e parte de A-12/A-18 UX.
- Escopo permitido: download autenticado de export completed; botões órfãos conectados ou `disabled data-status="planned"`; tipos de usage/plan atualizados; microcopy de empty/error/loading consistente.
- Escopo proibido: criar histórico global de exports se backend não tem endpoint; polling automático amplo; redesign visual; novas features fora da auditoria.
- Arquivos prováveis: `apps/web/lib/api.ts`, `apps/web/lib/types.ts`, `apps/web/app/o/[org]/p/[project]/exports/page.tsx`, `page.tsx` overview, `evaluations/page.tsx`, `traces/[trace]/page.tsx`, `datasets/page.tsx`, `apps/web/tests/security.test.mjs`.
- Comportamento esperado: export completed oferece download via endpoint autenticado; path local deixa de ser ação primária; botões sem handler ficam marcados como planejados ou viram links/actions reais; usage types incluem span/token/judge budget.
- Testes obrigatórios: typescript cobre campos novos; teste web garante botões planned ou links/actions; teste de download helper monta URL/headers corretamente se implementado.
- Comandos de validação: `cd apps/web && npm run test && npx tsc --noEmit && npm run build`.
- Critérios de aceite: nenhum botão ativo sem handler nos arquivos auditados; exports não diz que download não existe; tipos frontend batem com `routes_phase6.py`.
- Riscos: download autenticado em browser/server action precisa lidar com cookie/token sem expor bearer; histórico ainda limitado a IDs conhecidos.
- Rollback: revert frontend; backend não muda.
- Modelo recomendado: Sonnet/Codex medium.
- Effort recomendado: Medium.
- Prompt pronto para execução:

```text
Contexto:
Você está no EvalOps na fase Fix-7B.7. A auditoria apontou A-16 P2 e problemas de UX/contrato: a UI de exports diz que download não existe, mas o backend tem `/v1/exports/{id}/download`; há botões ativos sem handler em overview, evaluations e trace detail; tipos de usage/plan estão defasados.

Arquivos relevantes:
- apps/web/lib/api.ts
- apps/web/lib/types.ts
- apps/web/lib/actions.ts
- apps/web/app/o/[org]/p/[project]/exports/page.tsx
- apps/web/app/o/[org]/p/[project]/page.tsx
- apps/web/app/o/[org]/p/[project]/evaluations/page.tsx
- apps/web/app/o/[org]/p/[project]/traces/[trace]/page.tsx
- apps/web/app/o/[org]/p/[project]/datasets/page.tsx
- apps/web/tests/security.test.mjs
- apps/api/app/api/routes_phase6.py somente para ler contrato, não alterar.

Escopo permitido:
- Conectar download autenticado para exports completed ou criar server action segura para baixar.
- Remover microcopy obsoleta sobre ausência de download.
- Marcar botões órfãos como `disabled` + `data-status="planned"` ou conectar ação real já existente.
- Atualizar tipos `OrgSubscription` e `OrgUsage` com span/token/judge budget.
- Ajustar loading/empty/error copy sem redesign.

Escopo proibido:
- Não criar endpoint backend novo.
- Não implementar histórico global de exports.
- Não adicionar polling automático amplo.
- Não redesenhar layout nem mexer em paleta.
- Não tocar backend, SDK, Docker ou npm audit.

Testes:
- Typecheck cobre campos novos.
- Teste web verifica que botões auditados não ficam ativos sem ação.
- Download aparece apenas quando export está completed e não expirado, se essa informação estiver disponível.

Comandos:
- cd apps/web && npm run test
- cd apps/web && npx tsc --noEmit
- cd apps/web && npm run build

Documentação:
- Atualize somente README web se houver instrução obsoleta diretamente relacionada ao download.

Use a skill/ferramenta UI UX Pro Max para apoiar decisões de design, hierarquia visual, usabilidade, acessibilidade, consistência de componentes e estados de interface.

Relatório final esperado:
- Lista de telas ajustadas.
- Decisão sobre download autenticado.
- Botões conectados vs marcados planned.
- Testes executados e resultado.
```

### Fix-7B.8 — Deploy/Alembic/npm audit

- Objetivo: alinhar deploy com Alembic real e remover vulnerabilidades conhecidas via upgrade controlado.
- Achados cobertos: A-10, A-11.
- Escopo permitido: `docker-compose.prod.yml` com migration step; envs de Alembic; docs de deploy; upgrade controlado de Next/PostCSS com testes.
- Escopo proibido: `npm audit fix` automático, deploy real, troca completa de build pipeline, Kubernetes/Terraform, alteração de backend funcional não relacionada.
- Arquivos prováveis: `docker-compose.prod.yml`, `.env.example`, `README.md`, `docs/ops/database-migrations.md`, `apps/web/package.json`, lockfile.
- Comportamento esperado: produção roda `alembic upgrade head` antes de `uvicorn`; `EVALOPS_USE_ALEMBIC=1` definido onde apropriado; npm audit fica limpo ou vulnerabilidades aceitas documentadas; web build/test/tsc verdes.
- Testes obrigatórios: `alembic upgrade head` em DB efêmero; validação estrutural do compose; `npm audit --omit=dev`; `npm run build`; `npm run test`; `npx tsc --noEmit`.
- Comandos de validação: ver seção 5.
- Critérios de aceite: compose não contém comentário stale "Alembic não adotado"; migration step falha o container se schema não migrar; upgrade web é explícito, revisado e testado.
- Riscos: upgrade Next pode exigir mudanças de código; migration em startup pode gerar concorrência se múltiplas réplicas sobem ao mesmo tempo, então job único é preferível.
- Rollback: revert compose/package; se migration aplicada, seguir rollback Alembic documentado.
- Modelo recomendado: Opus/Codex high para deploy; Sonnet/Codex high para upgrade web.
- Effort recomendado: High.
- Prompt pronto para execução:

```text
Contexto:
Você está no EvalOps na fase Fix-7B.8. A auditoria apontou A-10 P1 e A-11 P1: `docker-compose.prod.yml` ainda diz que Alembic não foi adotado e não roda migration; `npm audit` aponta Next/PostCSS vulneráveis. Corrija deploy/audit de forma controlada.

Arquivos relevantes:
- docker-compose.prod.yml
- .env.example
- README.md
- docs/ops/database-migrations.md
- apps/api/alembic/
- apps/api/alembic.ini
- apps/web/package.json
- apps/web/package-lock.json ou lockfile existente

Escopo permitido:
- Atualizar compose para executar `alembic upgrade head` antes de `uvicorn` ou definir migration service/job único.
- Definir `EVALOPS_USE_ALEMBIC=1` e envs necessárias.
- Atualizar docs/env example sobre migration step.
- Atualizar Next/PostCSS de forma controlada, sem `npm audit fix` automático.
- Rodar build/test/typecheck/audit.

Escopo proibido:
- Não fazer deploy real.
- Não rodar `npm audit fix` automático.
- Não migrar para Kubernetes/Terraform.
- Não alterar código backend de negócio.
- Não misturar soft delete, quota, logout, SDK ou UX cleanup.

Testes:
- Alembic upgrade head em SQLite efêmero.
- Se Docker disponível, compose config/smoke Postgres.
- Web `npm audit --omit=dev`, `npx tsc`, build e tests.

Comandos:
- cd apps/api && DATABASE_URL=sqlite:///./tmp_fix7b_alembic.db alembic upgrade head
- docker compose -f docker-compose.prod.yml config
- cd apps/web && npm audit --omit=dev
- cd apps/web && npx tsc --noEmit
- cd apps/web && npm run build
- cd apps/web && npm run test

Documentação:
- Atualize docs de migration com o passo obrigatório antes do app.
- Registre decisão se migration rodar como service separado ou comando de entrypoint.

Use a skill/ferramenta UI UX Pro Max para apoiar decisões de design, hierarquia visual, usabilidade, acessibilidade, consistência de componentes e estados de interface.

Relatório final esperado:
- Estratégia de migration escolhida.
- Pacotes web atualizados e motivo.
- Resultado do npm audit.
- Comandos executados e resultado.
- Riscos de rollout/rollback.
```

### Fix-7B.9 — SDK reliability

- Objetivo: evitar perda silenciosa de telemetria no SDK Python.
- Achados cobertos: A-17.
- Escopo permitido: retry/backoff com jitter, tratamento de HTTP não-2xx, política de queue full, dead-letter opcional, logs/contadores simples, docs.
- Escopo proibido: mudança quebrante de API pública, dependência pesada, envio síncrono obrigatório, integração com backend novo.
- Arquivos prováveis: `packages/sdk-python/evalops/uploader.py`, `packages/sdk-python/evalops/tracer.py`, `packages/sdk-python/tests/test_sdk.py`, `packages/sdk-python/README.md`.
- Comportamento esperado: exceptions e 5xx têm retries; 4xx não fica em loop; queue full tem política documentada; eventos não enviados podem ir para dead-letter configurável; `flush()` reporta ou expõe falha de forma testável.
- Testes obrigatórios: 503 retry 3x; 400 não retry infinito; queue full incrementa drop/retorna indicador; dead-letter grava arquivo quando habilitado; API pública existente continua compatível.
- Comandos de validação: `python -m pytest packages/sdk-python/tests -q` ou backend venv equivalente.
- Critérios de aceite: nenhum drop silencioso sem contador/log/contrato; README documenta comportamento.
- Riscos: dead-letter pode gravar PII em disco; precisa ser opt-in ou path claro com alerta.
- Rollback: revert do pacote SDK.
- Modelo recomendado: Sonnet/Codex medium.
- Effort recomendado: Medium.
- Prompt pronto para execução:

```text
Contexto:
Você está no EvalOps na fase Fix-7B.9. A auditoria apontou A-17 P2: o SDK Python ignora queue full, exceções de rede e HTTP não-2xx, causando perda silenciosa de telemetria. Corrija somente confiabilidade do SDK.

Arquivos relevantes:
- packages/sdk-python/evalops/uploader.py
- packages/sdk-python/evalops/tracer.py
- packages/sdk-python/tests/test_sdk.py
- packages/sdk-python/README.md
- packages/sdk-python/pyproject.toml

Escopo permitido:
- Retry/backoff com jitter para falhas transitórias.
- Tratar status HTTP não-2xx.
- Política explícita para queue full: contador/log/retorno ou callback.
- Dead-letter opcional e documentado.
- Testes unitários com HTTP mock/local.

Escopo proibido:
- Não mudar API pública de `evalops.init`, `trace`, `span`, `flush`.
- Não depender de backend novo.
- Não tornar envio síncrono obrigatório.
- Não adicionar dependência pesada sem justificativa.
- Não mexer em backend, frontend, Docker ou npm.

Testes:
- 503 gera retries com backoff.
- 400/401 não entra em retry infinito e é reportado.
- Queue cheia não perde sem contador/contrato.
- Dead-letter opcional grava payload quando habilitado.
- Smoke HTTP existente continua verde.

Comandos:
- python -m pytest packages/sdk-python/tests -q
- Se o ambiente global não tiver pytest: cd apps/api && .venv/bin/python -m pytest ../../packages/sdk-python/tests -q

Documentação:
- Atualize README do SDK com retry/backoff, queue full, HTTP não-2xx e dead-letter.

Relatório final esperado:
- Comportamento novo do SDK.
- API pública preservada.
- Testes executados e resultado.
- Risco de PII em dead-letter e mitigação.
```

## 5. Comandos de validação por subfase

Backend:

```bash
# Fix-7B.1
cd apps/api && python -m pytest tests/test_phase10_audit_privacy_exports.py tests/test_phase5_prompts_datasets_experiments.py tests/test_phase4_rubrics_eval.py -q --tb=short -p no:warnings

# Fix-7B.2
cd apps/api && python -m pytest tests/test_phase9_auth_hardening.py -q --tb=short -p no:warnings

# Fix-7B.3
cd apps/api && python -m pytest tests/test_phase8_p0_security.py tests/test_phase9_auth_hardening.py tests/test_phase10_audit_privacy_exports.py tests/test_phase12_quota_eval_storage.py -q --tb=short -p no:warnings
cd apps/api && python -m pytest tests/test_health.py tests/test_auth_flow.py tests/test_phase1_identity_access.py tests/test_phase2_tracing.py tests/test_phase3_analytics.py tests/test_phase6_feedback_export_usage.py tests/test_phase7_e2e_mvp_flow.py -q --tb=short -p no:warnings

# Fix-7B.4
cd apps/api && python -m pytest tests/test_phase12_quota_eval_storage.py tests/test_phase8_p0_security.py tests/test_phase10_audit_privacy_exports.py -q --tb=short -p no:warnings

# Fix-7B.5
cd apps/api && python -m pytest tests/test_phase4_rubrics_eval.py tests/test_phase5_prompts_datasets_experiments.py tests/test_phase12_quota_eval_storage.py -q --tb=short -p no:warnings

# Fix-7B.6
cd apps/api && python -m pytest tests/test_phase8_p0_security.py tests/test_phase10_audit_privacy_exports.py tests/test_phase12_quota_eval_storage.py -q --tb=short -p no:warnings
```

Frontend:

```bash
# Fix-7B.2, Fix-7B.6, Fix-7B.7, Fix-7B.8
cd apps/web && npm run test
cd apps/web && npx tsc --noEmit
cd apps/web && npm run build
```

SDK:

```bash
# Fix-7B.9
python -m pytest packages/sdk-python/tests -q

# Fallback se pytest só existir no venv do backend
cd apps/api && .venv/bin/python -m pytest ../../packages/sdk-python/tests -q
```

npm audit:

```bash
# Fix-7B.8
cd apps/web && npm audit --omit=dev
cd apps/web && npm audit
```

Alembic/Docker:

```bash
# Fix-7B.8
cd apps/api && DATABASE_URL=sqlite:///./tmp_fix7b_alembic.db alembic upgrade head
docker compose -f docker-compose.prod.yml config

# Se Docker/Postgres estiver disponível
docker compose -f docker-compose.prod.yml up --build
```

Gate final antes de voltar para 7C:

```bash
cd apps/api && python -m pytest tests -q --tb=short -p no:warnings
cd apps/web && npm audit --omit=dev && npm run test && npx tsc --noEmit && npm run build
python -m pytest packages/sdk-python/tests -q
```

## 6. O que NÃO fazer

- Não implementar features novas.
- Não continuar 7C antes de fechar os P0/P1.
- Não criar arquitetura hexagonal/DDD pesada, repositories artificiais ou ports/adapters.
- Não rodar `npm audit fix` automático.
- Não fazer deploy.
- Não misturar todas as correções num PR gigante.
- Não fazer hard delete/purge físico de traces como atalho para soft delete.
- Não trocar SQLite dev/test por Postgres obrigatório.
- Não esconder SQLite locks pulando testes sem substituição.
- Não criar Redis, Celery/RQ, S3 ou OpenTelemetry dentro do Fix-7B.
- Não alterar testes para aceitar comportamento inseguro.
- Não fazer commit nem push sem pedido explícito.

## 7. Estratégia de branches

Recomendação preferida:

- Manter `fix-7b` como branch guarda-chuva de planejamento e coordenação.
- Criar uma branch por subfase a partir de `fix-7b` ou de `main`, por exemplo `fix-7b/03-test-isolation`, `fix-7b/01-soft-delete`, `fix-7b/02-logout`.
- Abrir PRs pequenos, um por subfase, com validação própria e sem mudanças de outras subfases.

Alternativa aceitável para time pequeno:

- Trabalhar em uma única branch `fix-7b`, mas com commits separados por subfase.
- Ordem dos commits deve seguir a seção 2.
- Não acumular todos os P0/P1 sem revisão intermediária.

## 8. Checklist antes de voltar para 7C

- [ ] Fix-7B.3 concluída: backend tests rodam sem SQLite lock como gate confiável.
- [ ] Fix-7B.1 concluída: nenhum fluxo operacional retorna traces soft-deletados.
- [ ] Fix-7B.2 concluída: dashboard chama `/v1/auth/logout` e revoga JWT.
- [ ] Fix-7B.4 concluída: quota check+increment é transacionalmente consistente.
- [ ] Fix-7B.5 concluída: LLM judge budget/custo tem contrato real e tests.
- [ ] Fix-7B.8 concluída ou explicitamente aprovada para PR paralelo: Alembic/npm blockers resolvidos.
- [ ] P0/P1 da auditoria A-01 a A-11 fechados ou formalmente reclassificados.
- [ ] Backend, frontend e SDK gates relevantes registrados no PR.
- [ ] Nenhuma correção depende de `rm -f evalops.db*` manual para passar.
- [ ] Roadmap/baseline atualizados após implementação, não durante este plano.

## 9. Checklist antes de deploy

- [ ] `alembic upgrade head` executa em DB vazio e o processo de deploy falha se migration falhar.
- [ ] `docker-compose.prod.yml` ou job equivalente define migration step único antes do app.
- [ ] `EVALOPS_USE_ALEMBIC=1`, `DATABASE_URL`, `JWT_SECRET` e `EVALOPS_EXPORTS_DIR` configurados para produção.
- [ ] Export de traces soft-deletados bloqueado por teste.
- [ ] Dataset build e listagem de evaluations respeitam soft delete.
- [ ] Logout web revoga JWT e reuso do token retorna 401.
- [ ] Quota/concurrency validada em Postgres ou staging equivalente.
- [ ] LLM judge não contorna budget e registra custo.
- [ ] Erros públicos sanitizados; UI não mostra SQL/path/stack.
- [ ] Redaction opt-in cobre superfície PII documentada.
- [ ] `npm audit --omit=dev` sem high/moderate não aceitas.
- [ ] `npm run test`, `npx tsc --noEmit` e `npm run build` verdes.
- [ ] SDK retry/dead-letter documentado se SDK for parte do release.
- [ ] Storage persistente de exports configurado e com retenção definida.
- [ ] Rate limit/proxy trust reavaliado para topologia real.
- [ ] Plano de rollback de app, web e migrations documentado.
