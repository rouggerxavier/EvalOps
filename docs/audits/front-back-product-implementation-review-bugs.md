# Bugs encontrados na implementação front-back-product

Este documento acompanha os bugs encontrados durante o code review dos commits
da implementação do plano `front-back-product`.

Plano: [docs/implementações.md](../implementações.md)
Auditoria base: [front-back-product-audit-2026-05-21.md](./front-back-product-audit-2026-05-21.md)
Branch: `feat/front-back-product-implementation`

## Resumo

Todos os bugs do review foram fechados:

| Bug | Status | Commit de correção |
|-----|--------|--------------------|
| 1.1 — `cost_by_day` x KPIs em 24h | fechado | `d93d632` |
| 2.1 — contrato RAG lista x detalhe | fechado | `2388608` |
| 2.2 — `slow_kind` não persiste | fechado | `c084831` |
| 3.1 — teste keys frágil | fechado | `1a707ed` |
| 4.1 — Novo projeto fora do switcher | fechado | `c084831` |
| 4.2 — slug duplicado genérico | fechado | `c084831` |
| 5.1 — env não filtra dados | fechado | `c084831` |
| 5.2 — sidebar `online` estático | fechado | `c084831` |
| 6.1 — `_classify_cost_source` erra casos | fechado | `0a63dea` |
| 6.2 — `cost_source` ausente no detalhe | fechado | `0a63dea` |
| 7.1 — tabela de status do plano | fechado | este commit |
| 7.2 — `npm run test` web falhando | fechado | `1a707ed` |

## Fase 1 - Overview window

Commit revisado: `be68ec6` - `feat(analytics): aplica window=24h|7d|30d em /analytics/overview`

### Bug 1.1 - `cost_by_day` pode divergir dos KPIs em `window=24h`

Status: fechado

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

Status: fechado

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

Status: fechado

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

Status: fechado

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

Commit revisado: `c6cba23` - `feat(projects): UI para criar novo projeto direto do settings da organização`

### Bug 4.1 - `Novo projeto` nao foi conectado ao workspace/sidebar

Status: fechado

O commit cria o formulario de novo projeto dentro de Settings, mas nao adiciona
a entrada de criacao no workspace switcher ou na sidebar, que era o ponto
principal do fluxo pedido. No estado revisado, o `WorkspaceSwitcher` continua
listando apenas projetos existentes e a sidebar mostra o workspace atual como um
link para o projeto ativo.

Evidencia:
- O diff do commit altera `settings/page.tsx`, `lib/actions.ts`, `lib/api.ts` e
  `settings-create-project.test.mjs`, mas nao altera `Sidebar.tsx`,
  `EvoTopbar.tsx` ou `WorkspaceSwitcher.tsx`.
- `WorkspaceSwitcher` apenas faz `projects.map(...)` para renderizar opcoes
  existentes.
- `EvoTopbar` so renderiza o switcher quando `projects.length > 1`, entao uma
  conta com apenas o projeto default nao ve nenhum ponto de troca/criacao ali.

Risco:
- O usuario que clica em `Workspace - {org}` / projeto default nao encontra o
  caminho para criar outro projeto.
- A fase fica parcialmente entregue: a criacao existe por Settings, mas nao no
  fluxo de produto especificado para workspace/sidebar.

Correção esperada:
- Adicionar uma entrada `Novo projeto` no workspace switcher/sidebar apontando
  para o formulario, uma rota/modal de criacao, ou uma acao equivalente.
- Garantir que a entrada exista tambem quando ha apenas um projeto.
- Adicionar teste source cobrindo a entrada no switcher/sidebar, nao apenas o
  card de Settings.

### Bug 4.2 - Slug duplicado ainda retorna mensagem generica

Status: fechado

O backend retorna `project_slug_taken` para slug duplicado, mas o frontend
sanitiza todo erro HTTP 409 para uma mensagem generica de conflito. Isso evita
vazamento de erro bruto, mas nao cumpre a DoD de erro legivel para slug
duplicado.

Evidencia:
- `apps/api/app/api/routes.py` retorna 409 com `detail="project_slug_taken"`.
- `apps/web/lib/api.ts` transforma falhas em `Error("API 409: ...")`.
- `apps/web/lib/safe-error.ts` mapeia qualquer 409 para
  `Conflito: o recurso já existe ou foi modificado.`
- `settings-create-project.test.mjs` so valida que o fallback nao quebra; nao
  exige uma copy especifica para slug duplicado.

Risco:
- Ao tentar criar um segundo projeto com slug ja usado, o usuario nao entende
  qual campo corrigir.
- O fluxo parece falhar por conflito generico, apesar de o backend ter um
  motivo especifico e acionavel.

Correção esperada:
- Preservar seguranca do sanitizer, mas mapear `project_slug_taken` para uma
  mensagem especifica, por exemplo `Este slug ja esta em uso nesta organizacao.`
- Adicionar teste cobrindo o tratamento de `project_slug_taken` no action/client
  ou no utilitario de erro.

## Fase 5 - Notificacoes, ambiente e health

Commit revisado: `1f31e6a` - `feat(shell): notif "Marcar lidas", seletor de ambiente real e página /health`

### Bug 5.1 - Seletor de ambiente muda o chip, mas nao muda os dados

Status: fechado

O seletor do topbar passou a gravar `evalops_env` em cookie e redirecionar com
`env={valor}`, mas as paginas que filtram dados leem `searchParams.environment`.
Na pratica, trocar o ambiente pode atualizar o chip do topbar apos refresh, mas
nao altera o universo de Overview/Traces.

Evidencia:
- `apps/web/lib/actions.ts` redireciona `setEnvironmentAction` com
  `{ env: environment }`.
- `apps/web/app/o/[org]/p/[project]/page.tsx` usa `qp.environment` para chamar
  `getOverview(...)` e `getTraces(...)`.
- `apps/web/app/o/[org]/p/[project]/traces/page.tsx` tambem usa
  `qp.environment`; nao le o cookie `evalops_env`.
- `EvoTopbar` envia `current_path` como `pathname`, sem query string.

Risco:
- A DoD "Ambiente escolhido altera dados visiveis" nao fecha.
- Usuario ve `prod`, `staging` ou `dev` no chip, mas os cards/listas continuam
  mostrando `todos` ou o filtro anterior.

Correção esperada:
- Escolher uma unica fonte de verdade: redirecionar para `?environment=...` e
  preservar demais parametros, ou fazer as paginas server-side lerem o cookie de
  forma consistente.
- Adicionar teste source que prove que o action usa `environment`, nao `env`, e
  que Overview/Traces recebem o mesmo valor selecionado.

### Bug 5.2 - Status estatico do sidebar continua dizendo `online`

Status: fechado

O commit criou `/health`, mas manteve no sidebar o status estatico `SDK Python`
`online - ingestao pronta` sem depender do probe real. Isso conflita com o
escopo da fase, que pedia remover status estatico se nao houvesse check real.

Evidencia:
- `apps/web/components/Sidebar.tsx` ainda renderiza `sb-status__pulse`,
  `SDK Python` e `online - ingestao pronta` como texto fixo.
- A nova pagina `/health` nao e usada por esse status do sidebar.

Risco:
- A UI pode declarar sistema online quando readiness/liveness falham.
- Usuario perde confianca no novo `/health`, porque outra parte fixa da shell
  continua fazendo promessa operacional sem fonte real.

Correção esperada:
- Transformar o footer em link para `/health` com copy neutra, ou remover a
  promessa `online` ate existir health real nessa area.
- Adicionar teste source garantindo que o sidebar nao contenha status operacional
  hardcoded.

## Fase 6 - Custo, tokens e exports

Commit revisado: `698b6a3` - `feat(exports/cost): file_size_bytes em exports + origem do custo no trace`

### Bug 6.1 - Origem do custo e inferida do agregado e classifica casos reais errado

Status: fechado

`_classify_cost_source(trace)` olha apenas `total_cost_usd` e tokens agregados.
Com isso, um custo enviado pelo cliente em `span.cost_usd` vira `priced`, e um
custo realmente precificado que arredonde para zero pode virar `estimated`.
Tambem nao existe `provided`, embora a fase tenha definido esse estado.

Evidencia:
- `apps/api/app/domain/services/trace_ingest_service.py` diferencia internamente
  `span_in.cost_usd is None` de custo fornecido pelo cliente.
- `apps/api/app/api/routes.py` descarta essa origem e classifica apenas por
  `total_cost_usd > 0` ou tokens agregados.
- O contrato implementado retorna `priced | estimated | unknown`, sem
  `provided`.

Risco:
- Custo fornecido pelo SDK/cliente aparece como se tivesse sido precificado pela
  tabela interna.
- Provider/model precificado com custo muito pequeno pode receber badge
  `estimado`, apesar de haver pricing real.
- A UI continua sem distinguir medicao real, preco calculado e estimativa.

Correção esperada:
- Persistir ou derivar a origem em nivel de span/trace, com os estados
  `provided`, `priced`, `estimated` e `unknown`.
- Adicionar regressao para span com `cost_usd` fornecido, span com pricing da
  tabela, modelo desconhecido com tokens e trace sem tokens.

### Bug 6.2 - Origem de custo/tokens nao aparece no detalhe do trace

Status: fechado

O badge de origem foi adicionado apenas na tabela de traces. A pagina de detalhe
continua exibindo `Custo` e tokens sem informar se o valor foi precificado,
fornecido, estimado ou desconhecido.

Evidencia:
- `apps/api/app/api/routes.py` adiciona `cost_source` nos itens de
  `/v1/traces`, mas `get_trace` retorna `TraceOut.model_validate(trace)` sem
  `cost_source`.
- `apps/api/app/schemas.py` nao inclui `cost_source` em `TraceOut`.
- `apps/web/app/o/[org]/p/[project]/traces/[trace]/page.tsx` renderiza o metric
  `Custo` apenas com `formatCost(t.total_cost_usd)`.

Risco:
- A DoD "Custo exibido informa origem" fica verdadeira so na lista, nao no
  detalhe onde o usuario investiga o trace.
- Tokens estimados continuam sendo apresentados como contagem comum no detalhe.

Correção esperada:
- Expor `cost_source` tambem no detalhe e renderizar badge/tooltip no metric de
  custo.
- Se tokens puderem ser estimados, expor a origem dos tokens ou copy explicita
  para nao apresentar estimativa como medicao real.

## Fase 7 - Copy, QA e status do plano

Commit revisado: `ab2b1b5` - `chore(copy): renomeia/remova ações sem efeito real + status do plano`

### Bug 7.1 - Tabela de status do plano marca fases incompletas como `ok`

Status: fechado

O commit atualiza `docs/implementações.md` com status final, mas marca fases com
bugs abertos como `ok` e deixa pendencias conhecidas incompletas.

Evidencia:
- A tabela marca Fase 4 como `ok`, apesar de `Novo projeto` nao estar conectado
  ao workspace/sidebar e slug duplicado continuar generico.
- A tabela marca Fase 5 como `ok`, apesar do seletor de ambiente nao filtrar
  dados e o sidebar manter status operacional hardcoded.
- A lista de pendencias conhecidas menciona Fase 1, parte da Fase 2 e Fase 6,
  mas omite os achados de Fase 3, Fase 4, Fase 5 e `slow_kind`.

Risco:
- O plano passa uma falsa sensacao de pronto para PR/merge.
- A etapa de correcao pode esquecer bugs ja identificados no review.

Correção esperada:
- Atualizar `docs/implementações.md` depois das correcoes, ou marcar as fases
  afetadas como `parcial` enquanto houver bug aberto.
- Sincronizar a lista de pendencias com este arquivo de review.

### Bug 7.2 - `npm run test` do web ainda falha no estado final da branch

Status: fechado

Mesmo depois do commit de copy/QA, o comando padrao de testes do pacote web nao
fecha. A maioria das falhas parece vir de testes source antigos que ainda
esperam copies/classes de fases anteriores, mas enquanto eles estiverem no suite
o status final nao pode ser tratado como verde.

Evidencia:
- `cd apps/web && npm run test` retornou exit code 1.
- Resultado observado: 180 testes, 134 pass, 46 fail.
- As falhas incluem arquivos como `app-shell.test.mjs`, `datasets-p7.test.mjs`,
  `evaluations-p7.test.mjs`, `overview-p7.test.mjs`, `prompts-p7.test.mjs`,
  `rubrics-p7.test.mjs`, `security.test.mjs` e `ux-polish-p6.test.mjs`.

Risco:
- A branch fica sem um sinal basico de regressao para frontend.
- Falhas stale podem esconder falhas reais dos commits novos.

Correção esperada:
- Revisar os testes source obsoletos, removendo ou atualizando expectativas que
  nao representam mais o produto.
- Manter os testes que cobrem contratos reais dos commits atuais.
- Rodar `npm run test` verde antes de marcar QA final como concluido.
