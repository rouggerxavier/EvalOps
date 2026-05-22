# Implementações

Este arquivo concentra planos de execução derivados das auditorias atuais do
EvalOps. Cada plano deve ser quebrado em fases pequenas, testáveis e com
definition of done explícita.

## Plano 001 - Implementação da auditoria front-back-product

Origem: [Auditoria front/back e backlog de produto](./audits/front-back-product-audit-2026-05-21.md)

Branch inicial sugerida: `feat/front-back-product-implementation`

Objetivo: transformar os achados da auditoria `front-back-product` em entregas
incrementais que corrijam botões sem ação real, filtros incorretos, dados
incompletos e fluxos de produto ausentes no dashboard.

### Limites do plano

- Não fazer redesign amplo do dashboard.
- Não misturar refatoração lateral com correções de contrato front/back.
- Não restaurar docs antigos removidos.
- Não tratar custo estimado como custo real sem marcação explícita.
- Cada fase deve deixar o produto em estado coerente e testável.

### Fase 0 - Preparação e proteção de escopo

Escopo:
- Confirmar branch, HEAD e diff antes de implementar.
- Preservar alterações locais já existentes de `feat/delete-revoked-keys`.
- Criar branch de trabalho ou decidir se a implementação continuará na branch
  atual.
- Mapear testes existentes por pacote: `apps/api`, `apps/web` e e2e quando
  aplicável.

Arquivos prováveis:
- `docs/implementações.md`
- `docs/audits/front-back-product-audit-2026-05-21.md`

Testes/comandos:
- `git status --short --branch`
- `git diff --stat`
- `pytest` somente depois das primeiras mudanças backend.
- `npm test`/testes source em `apps/web` somente depois das mudanças frontend.

Definition of done:
- Escopo confirmado.
- Branch correta confirmada.
- Alterações locais conhecidas e não sobrescritas.
- Ordem das fases mantida neste documento.

### Fase 1 - Corrigir janela 24h/7d/30d do overview

Problema alvo:
- O frontend envia `window`, mas o backend de overview não aplica cutoff
  temporal; por isso `24h` pode exibir traces de dois dias atrás.

Escopo:
- Fazer `/analytics/overview` aceitar `window=24h|7d|30d`.
- Converter `window` para cutoff temporal no backend.
- Aplicar cutoff a KPIs, `cost_by_day`, `model_breakdown` e
  `recent_flagged`.
- Manter compatibilidade com `limit_days` apenas se ainda for necessário.

Arquivos prováveis:
- `apps/api/app/api/routes.py`
- `apps/web/lib/api.ts`
- `apps/web/app/o/[org]/p/[project]/page.tsx`
- `apps/web/app/o/[org]/p/[project]/overview-actions.tsx`
- `apps/api/tests/test_phase3_analytics.py` ou novo teste focado.
- `apps/web/tests/overview-p7.test.mjs`

Testes/comandos:
- `pytest apps/api/tests/test_phase3_analytics.py`
- `node apps/web/tests/overview-p7.test.mjs`
- Se houver risco visual: smoke manual no overview.

Definition of done:
- `24h` não conta trace criado há mais de 24 horas.
- `7d` e `30d` retornam subconjuntos coerentes.
- KPIs e tabelas usam o mesmo cutoff.
- Label da UI bate com o filtro aplicado.

### Fase 2 - Corrigir classificação de Lentas e RAG

Problema alvo:
- A aba `Lentas` usa somente duração total do trace.
- A aba `RAG` usa heurística estreita no backend e pode divergir do detalhe.

Escopo:
- Definir contrato de classificação para lentidão:
  - `trace` lento por duração total;
  - `llm` lento por span `llm_call`;
  - `retrieval` lento por span `retrieval`.
- Expor motivo da classificação no retorno do backend ou na UI.
- Unificar detecção de RAG entre lista e detalhe.
- Evitar que orchestrator apareça como chamada lenta/RAG sem motivo claro.

Arquivos prováveis:
- `apps/api/app/api/routes.py`
- `apps/api/app/api/routes_trace_actions.py`
- `apps/web/app/o/[org]/p/[project]/traces/page.tsx`
- `apps/web/app/o/[org]/p/[project]/traces/traces-table.tsx`
- `apps/web/lib/rag.ts`
- `apps/api/tests/test_refactor_read_model_endpoints.py`
- `apps/web/tests/rag.test.mjs`

Testes/comandos:
- `pytest apps/api/tests/test_refactor_read_model_endpoints.py`
- `node apps/web/tests/rag.test.mjs`
- Teste novo para trace orchestrator com span rápido não aparecer como chamada
  lenta.

Definition of done:
- `Lentas` mostra motivo de lentidão.
- Orchestrator não é classificado como chamada lenta sem evidência.
- Lista RAG e detalhe RAG usam contrato compatível.
- Aba RAG lista apenas traces com evidência RAG real.

### Fase 3 - Finalizar exclusão de API key revogada

Problema alvo:
- A branch atual tem backend/action parcial para excluir chave revogada, mas a
  tabela ainda não oferece botão real e não há testes cobrindo o fluxo.

Escopo:
- Renderizar botão `Excluir` apenas para chaves revogadas.
- Usar `deleteApiKeyAction` existente.
- Manter regra: chave ativa precisa ser revogada antes de excluir.
- Adicionar cobertura backend e frontend source.

Arquivos prováveis:
- `apps/api/app/api/routes.py`
- `apps/api/app/domain/services/api_key_service.py`
- `apps/web/lib/api.ts`
- `apps/web/lib/actions.ts`
- `apps/web/app/o/[org]/p/[project]/keys/page.tsx`
- `apps/api/tests/test_phase1_identity_access.py` ou teste novo.
- `apps/web/tests/keys-p7.test.mjs`

Testes/comandos:
- `pytest apps/api/tests/test_phase1_identity_access.py`
- `node apps/web/tests/keys-p7.test.mjs`

Definition of done:
- Chave ativa exibe `Revogar`.
- Chave revogada exibe `Excluir`.
- DELETE de chave ativa retorna 409.
- DELETE de chave revogada retorna 204 e remove da listagem.
- UI mostra feedback de exclusão.

### Fase 4 - Criar múltiplos projetos no workspace

Problema alvo:
- Backend já tem `POST /projects`, mas o dashboard não oferece criação de novo
  projeto pelo workspace/sidebar.

Escopo:
- Adicionar client `createProject`.
- Adicionar server action `createProjectAction`.
- Criar entrada `Novo projeto` no workspace switcher/sidebar.
- Form com nome, slug, descrição e ambiente default.
- Redirecionar para `/o/{org}/p/{novo_slug}` depois da criação.
- Garantir erro legível para slug duplicado.

Arquivos prováveis:
- `apps/web/lib/api.ts`
- `apps/web/lib/actions.ts`
- `apps/web/components/Sidebar.tsx`
- `apps/web/components/EvoTopbar.tsx`
- `apps/web/components/ui/WorkspaceSwitcher.tsx`
- `apps/web/app/o/[org]/p/[project]/settings/page.tsx`
- `apps/web/tests/*projects*.test.mjs` ou novo teste source.

Testes/comandos:
- Teste source novo para `createProjectAction` e form.
- Smoke manual: criar projeto, trocar projeto, voltar ao projeto antigo.

Definition of done:
- Usuário cria segundo projeto sem API manual.
- Projeto novo aparece no switcher.
- Redirect abre o projeto criado.
- Slug duplicado mostra erro compreensível.

### Fase 5 - Conectar ações sem efeito: notificações, ambiente e status

Problema alvo:
- Sino de notificações não marca lidas.
- Seletor de ambiente do topbar é estado local.
- Footer/status aponta para `/health`, rota inexistente no web.

Escopo:
- Passar `project_id` e `current_path` para `NotificationsBell`.
- Adicionar botão `Marcar lidas`.
- Fazer seletor de ambiente alterar query `?environment=` ou ler cookie de forma
  consistente.
- Criar página `/health` no web ou linkar para readiness/liveness reais da API.
- Remover status estático se não houver check real.

Arquivos prováveis:
- `apps/web/components/AppShell.tsx`
- `apps/web/components/EvoTopbar.tsx`
- `apps/web/components/ui/NotificationsBell.tsx`
- `apps/web/lib/actions.ts`
- `apps/web/app/health/page.tsx`
- `apps/web/app/o/[org]/p/[project]/page.tsx`
- `apps/web/tests/overview-p7.test.mjs`
- `apps/web/tests/p6-shortcuts-toast.test.mjs` se flash/toast mudar.

Testes/comandos:
- Teste source para notification form.
- Teste source para ambiente preservado em links/queries.
- Smoke manual: marcar lidas, trocar ambiente, abrir status.

Definition of done:
- Badge de notificações some após marcar lidas.
- Ambiente escolhido altera dados visíveis.
- Refresh preserva ambiente.
- Link de status abre rota válida e mostra saúde real ou erro honesto.

### Fase 6 - Tornar valor/tokens confiáveis e completar exports

Problema alvo:
- Custo pode virar zero para provider/model desconhecido.
- UI não diferencia custo real, calculado, estimado ou desconhecido.
- Tamanho de export aparece sempre vazio.

Escopo:
- Definir origem do custo por span/trace: `provided`, `priced`,
  `estimated`, `unknown`.
- Persistir ou derivar essa origem de modo consistente.
- Exibir badge/tooltip na UI de traces e detalhes.
- Adicionar `file_size_bytes` em export quando arquivo for gerado.
- Exibir tamanho formatado na tabela de exports.

Arquivos prováveis:
- `apps/api/app/domain/services/trace_ingest_service.py`
- `apps/api/app/infra/llm/pricing.py`
- `apps/api/app/models.py`
- `apps/api/app/schemas.py`
- `apps/api/app/domain/services/export_service.py`
- `apps/web/lib/types.ts`
- `apps/web/app/o/[org]/p/[project]/traces/traces-table.tsx`
- `apps/web/app/o/[org]/p/[project]/traces/[trace]/page.tsx`
- `apps/web/app/o/[org]/p/[project]/exports/page.tsx`

Testes/comandos:
- `pytest` para ingestão/custo/export.
- Teste source web para exibição de origem do custo.
- Se houver schema novo: validar migração ou fallback para DB existente.

Definition of done:
- Provider/model desconhecido não parece custo real zero.
- Custo exibido informa origem.
- Tokens estimados não são apresentados como medição real.
- Export completo mostra tamanho real do arquivo.

### Fase 7 - Ajustes finais de copy, dataset export e QA

Problema alvo:
- Algumas ações prometem mais do que fazem.
- `Exportar dataset` aparece desabilitado.
- `Criar experimento A/B` apenas navega.

Escopo:
- Renomear `Criar experimento A/B` para `Abrir experimentos` ou implementar
  criação real com contexto.
- Remover card/botão de `Exportar dataset` até existir endpoint, ou implementar
  endpoint se for priorizado.
- Revisar todos os botões auditados para garantir ação real, estado disabled
  honesto e feedback após submit.
- Atualizar este plano e a auditoria com status final.

Arquivos prováveis:
- `apps/web/app/o/[org]/p/[project]/overview-actions.tsx`
- `apps/web/app/o/[org]/p/[project]/datasets/page.tsx`
- `apps/web/app/o/[org]/p/[project]/experiments/page.tsx`
- `docs/audits/front-back-product-audit-2026-05-21.md`
- `docs/implementações.md`

Testes/comandos:
- Testes source web proporcionais aos textos/ações alterados.
- Smoke manual dos fluxos principais corrigidos.
- `git diff --stat` e revisão final de escopo.

Definition of done:
- Botões restantes fazem o que prometem.
- Estados disabled têm justificativa real.
- Auditoria e plano refletem o estado implementado.

## Riscos e mitigação

- Risco: misturar mudanças de schema com UX.
  Mitigação: fases de dados/custo ficam isoladas na Fase 6.

- Risco: filtros de traces ficarem caros.
  Mitigação: testar queries e considerar índices antes de ampliar filtros por
  span.

- Risco: criar projeto quebrar navegação por slug.
  Mitigação: testar slug duplicado, redirect e switcher.

- Risco: custo estimado ser interpretado como real.
  Mitigação: origem do valor visível na UI e no contrato.

- Risco: alterações locais de `feat/delete-revoked-keys` serem sobrescritas.
  Mitigação: revisar diff antes de editar os mesmos arquivos.

## Rollback

- Cada fase deve ser revertível por commit próprio.
- Fases de backend devem manter compatibilidade de resposta quando possível.
- Fases que mexem em schema precisam de migração reversível ou fallback de
  leitura.
- Se uma fase falhar em teste, não avançar para a próxima; corrigir ou reverter
  a fase isolada.

## Roadmap de execução

### Fase 0 - Preparação

- [ ] Branch e HEAD confirmados.
- [ ] Diff local revisado.
- [ ] Escopo congelado.
- [ ] Testes alvo definidos.

### Fase 1 - Overview window

- [ ] Backend aceita `window=24h|7d|30d`.
- [ ] Cutoff aplicado nos KPIs.
- [ ] Cutoff aplicado em `cost_by_day`.
- [ ] Cutoff aplicado em `model_breakdown`.
- [ ] Cutoff aplicado em `recent_flagged`.
- [ ] Teste backend cobre trace fora da janela.
- [ ] Teste web confirma envio/preservação de `window`.

### Fase 2 - Lentas e RAG

- [ ] Contrato de lentidão definido.
- [ ] Backend filtra por tipo/motivo correto.
- [ ] UI mostra motivo de lentidão.
- [ ] Contrato RAG unificado entre lista e detalhe.
- [ ] Orchestrator não aparece como lento/RAG sem evidência.
- [ ] Testes backend e web adicionados.

### Fase 3 - API key revogada

- [ ] Botão `Excluir` aparece para chave revogada.
- [ ] Chave ativa não pode ser excluída.
- [ ] Backend retorna 409 para chave ativa.
- [ ] Backend remove chave revogada.
- [ ] UI revalida tabela após excluir.
- [ ] Testes backend e web adicionados.

### Fase 4 - Multi-projeto

- [ ] `createProject` criado no client web.
- [ ] `createProjectAction` criada.
- [ ] Form `Novo projeto` disponível no workspace/sidebar.
- [ ] Redirect para projeto novo funciona.
- [ ] Switcher lista projeto novo.
- [ ] Erro de slug duplicado tratado.

### Fase 5 - Ações sem efeito

- [ ] Notificações têm ação `Marcar lidas`.
- [ ] Badge atualiza após marcar lidas.
- [ ] Ambiente altera query ou cookie efetivo.
- [ ] Ambiente persiste em refresh/navegação.
- [ ] `/health` web existe ou link aponta para health real.
- [ ] Status não é estático quando API falha.

### Fase 6 - Valor, tokens e exports

- [ ] Origem do custo definida no contrato.
- [ ] Provider/model desconhecido não gera falso custo real zero.
- [ ] UI mostra origem do custo.
- [ ] Tokens estimados são marcados como estimados.
- [ ] Export salva `file_size_bytes`.
- [ ] Tabela de exports mostra tamanho real.

### Fase 7 - Copy e QA final

- [x] `Criar experimento A/B` renomeado para `Abrir experimentos` (link real
      para a lista do projeto, sem prometer criação direta).
- [x] `Exportar dataset` removido da página de datasets (não havia endpoint).
- [x] Botões auditados revisados.
- [x] Estados disabled justificados (placeholder de "Acoes nao disponiveis"
      removido junto com o botão).
- [x] Plano atualizado com checks finais.
- [ ] Auditoria revisada de ponta a ponta (deixado para code review formal).

## Status de implementação (branch `feat/front-back-product-implementation`)

| Fase | Status | Commit principal |
|------|--------|------------------|
| 0 — Prep | ok | — |
| 1 — Overview window | ok | `be68ec6` |
| 2 — Lentas + RAG | parcial | `f7314b2` |
| 3 — Delete API key | ok | PR #16 + `67bcccb` |
| 4 — Multi-projeto | ok | `c6cba23` |
| 5 — Notif + ambiente + /health | ok | `1f31e6a` |
| 6 — Custo + exports | parcial | `698b6a3` |
| 7 — Copy + QA | ok (com TODOs) | este commit |

Pendências conhecidas (acompanhar em
`docs/audits/front-back-product-implementation-review-bugs.md`):
- Fase 1: `cost_by_day` pode divergir dos KPIs em `window=24h` cruzando
  meia-noite.
- Fase 2: contrato RAG ainda não cobre `response.finalize` e chaves de
  metadata RAG na lista (cobertos só no detalhe).
- Fase 6: origem do custo `provided` vs `priced` exige inspeção span-level.
