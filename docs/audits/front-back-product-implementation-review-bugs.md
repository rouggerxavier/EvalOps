# Bugs encontrados na implementação front-back-product

Este documento acompanha os bugs encontrados durante o code review dos commits
da implementação do plano `front-back-product`.

Plano: [docs/implementações.md](../implementações.md)
Auditoria base: [front-back-product-audit-2026-05-21.md](./front-back-product-audit-2026-05-21.md)
Branch: `feat/front-back-product-implementation`

## Fase 1 - Overview window

Commit revisado: `be68ec6` - `feat(analytics): aplica window=24h|7d|30d em /analytics/overview`

### Bug 1.1 - `cost_by_day` pode divergir dos KPIs em `window=24h`

Status: aberto

Se a janela de 24h atravessar meia-noite, os KPIs contam traces de hoje e de
ontem, mas `cost_by_day` pode retornar apenas o dia mais recente porque o
backend aplica `limit(day_cap)` com `day_cap = 1` depois do cutoff.

Evidencia:
- `apps/api/app/api/routes.py` calcula `day_cap = 1` para `window=24h`.
- `cost_by_day` agrupa por `date(created_at)` e aplica `.limit(day_cap)`.

Risco:
- O card/sparkline de volume e custo pode não somar o mesmo universo dos KPIs.
- O usuário vê `Traces = N`, mas a série diária representa menos traces.

Correção esperada:
- Para `window`, não limitar os buckets por `day_cap` depois do cutoff, ou
  permitir todos os dias calendário tocados pela janela.
- Adicionar regressão com dois traces dentro das últimas 24h, um em cada dia
  calendário, validando `sum(cost_by_day.traces) == kpis.traces`.

## Fase 2 - Lentas e RAG

Commit revisado: `f7314b2` - `feat(traces): classifica lentidão por origem (trace/llm/retrieval) + unifica RAG`

### Bug 2.1 - Filtro RAG da lista ainda não usa o mesmo contrato do detalhe

Status: aberto

O commit adiciona matching por spans `rag.%`, mas o detalhe considera mais
sinais como RAG: spans `response.finalize` e metadados como
`pipeline_version`, `retrieved_count`, `citation_count`, `grounding_ok`,
`quality_level`, `quality_score` e `support_rate`.

Evidencia:
- `apps/api/app/api/routes.py` filtra `rag=true` por `Trace.name ilike "rag.%"`,
  `metadata.is_rag` ou span `rag.%`.
- `apps/web/lib/rag.ts` classifica detalhe RAG também por `response.finalize` e
  chaves de metadata RAG.

Risco:
- Um trace pode abrir detalhe com aba/cards RAG, mas não aparecer na aba RAG da
  lista.
- A Fase 2 fica parcialmente entregue porque lista e detalhe ainda divergem.

Correção esperada:
- Centralizar o contrato RAG do backend para cobrir os mesmos sinais do detalhe,
  ou reduzir explicitamente o detalhe para o mesmo contrato.
- Adicionar regressões para trace com apenas `response.finalize` e para trace
  com metadata RAG sem span `rag.%`.

### Bug 2.2 - `slow_kind` não é preservado em paginação e filtros

Status: aberto

As sub-abas de lentidão geram URL com `slow_kind`, mas `baseParams` não guarda
esse parâmetro. Com isso, ao ir para próxima página, voltar para primeira página
ou submeter filtros, a tela volta implicitamente para `slow_kind=trace`.

Evidencia:
- `apps/web/app/o/[org]/p/[project]/traces/page.tsx` só adiciona
  `environment`, `name` e `status` em `baseParams`.
- `nextPageHref` e `firstPageHref` partem de `baseParams`.
- O formulário de filtros preserva `tab`, mas não preserva `slow_kind`.

Risco:
- Usuário seleciona `LLM call` ou `Retrieval`, pagina/filtra e passa a ver
  resultado de `Trace inteiro` sem perceber.
- O badge `LLM lento`/`retrieval lento` desaparece ou a lista muda de universo.

Correção esperada:
- Preservar `slow_kind` em `baseParams` quando `tab === "slow"` e
  `slowKind !== "trace"`.
- Adicionar `<input type="hidden" name="slow_kind" ...>` no formulário de
  filtros da aba slow.
- Adicionar teste source cobrindo links de paginação/filtro com
  `slow_kind=llm` e `slow_kind=retrieval`.

## Fase 3 - API key revogada

Commit revisado: `67bcccb` - `test(keys): atualiza source test de keys para cobrir delete + remove asserts stale`

### Bug 3.1 - Teste source nao garante que `Excluir` fica apenas no ramo revogado

Status: aberto

O produto atual renderiza `Revogar` para chave ativa e `Excluir` para chave
revogada, mas o teste adicionado no commit nao valida essa relacao de forma
estrutural. Ele procura `!key.revoked_at` seguido de `revokeApiKeyAction`, e
depois procura `deleteApiKeyAction`/`Excluir` em qualquer ponto da pagina. Uma
regressao que invertesse os formularios entre os ramos ativo e revogado ainda
poderia passar nesse teste, mesmo expondo uma acao destrutiva para chave ativa.

Evidencia:
- `apps/web/tests/keys-p7.test.mjs` valida `deleteApiKeyAction` e `Excluir` de
  forma global, sem amarrar ambos ao ramo `: (` do ternario de `key.revoked_at`.
- A pagina real usa o ternario em `apps/web/app/o/[org]/p/[project]/keys/page.tsx`
  para separar `revokeApiKeyAction` e `deleteApiKeyAction`.
- O backend protege DELETE ativo com 409, mas a DoD da fase tambem exige que a
  UI exiba `Excluir` apenas para chave revogada.

Risco:
- O teste daria falso positivo se a UI passasse a mostrar `Excluir` para chaves
  ativas.
- O usuario poderia tentar excluir uma chave ativa e receber erro 409, quebrando
  o fluxo esperado de revogar primeiro e excluir depois.

Correção esperada:
- Fortalecer o source test para provar que o ramo `!key.revoked_at ? (...)`
  contem `revokeApiKeyAction`/`Revogar` e que o ramo `: (...)` contem
  `deleteApiKeyAction`/`Excluir`.
- Manter a regressao backend existente para DELETE ativo 409 e DELETE revogado
  204/remocao da listagem.

## Fase 4 - Multi-projeto

Commit revisado: pendente
