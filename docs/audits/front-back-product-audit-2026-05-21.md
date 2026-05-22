# Auditoria front/back e backlog de produto

Data: 2026-05-21
Branch auditada: `feat/delete-revoked-keys`
Base: `main`/`origin/main` em `96ca9a3`
Escopo: botoes e fluxos do dashboard que nao executam acao real, retornam dados
incompletos, ou prometem mais do que o backend entrega.

## Veredito

O dashboard ja tem varios fluxos reais, mas ainda mistura tres tipos de UI:

1. controles que parecem funcionais e nao alteram produto;
2. controles que chamam backend, mas o backend ignora filtro ou retorna dados
   incompletos;
3. acoes parcialmente implementadas por alteracoes locais ainda sem UI final e
   sem testes.

Prioridade recomendada: corrigir primeiro filtros e classificacao de traces,
porque afetam confianca nos dados. Depois fechar multi-projeto/API keys e, por
fim, melhorar metricas, status e microcopy.

## P0 - Dados incorretos ou filtros que enganam

### Janela 24h/7d/30d do overview nao filtra dados

Evidencia:
- `apps/web/app/o/[org]/p/[project]/overview-actions.tsx` envia `window`.
- `apps/web/lib/api.ts` envia `window` para `/analytics/overview`.
- `apps/api/app/api/routes.py` em `analytics_overview` aceita `limit_days`,
  mas nao aceita `window` e nao aplica cutoff temporal em `rows`, KPIs,
  breakdown de modelo ou flagged recentes.

Impacto:
- Selecionar "Ultimas 24h" pode continuar mostrando traces de dois dias atras.
- KPIs, custo, latencia p95 e erros deixam de ser confiaveis.

Correcao recomendada:
- Trocar ou complementar `limit_days` por `window: 24h|7d|30d`.
- Calcular `cutoff = now - window`.
- Aplicar cutoff em todas as queries do overview: traces base, series por dia,
  breakdown de modelo e flagged recentes.
- Adicionar teste de backend com trace antigo fora da janela e teste web que
  preserve o envio de `window`.

Definition of done:
- `24h` nao retorna nem conta trace de 2 dias atras.
- `7d` e `30d` retornam subconjuntos coerentes.
- A label da UI bate com o filtro realmente aplicado.

### Aba "Lentas" classifica traces por duracao total fixa

Evidencia:
- `apps/web/app/o/[org]/p/[project]/traces/page.tsx` usa
  `duration_gt=2000` na aba `slow`.
- `apps/api/app/api/routes.py` filtra `Trace.duration_ms > duration_gt`.
- A tabela colore latencia acima de `2000ms` como warning e acima de `4000ms`
  como danger.

Impacto:
- Chamadas de orchestrator podem entrar como lentas mesmo quando os spans de
  LLM/RAG nao foram lentos.
- O usuario ve "todas foram para lentas" se o trace total inclui espera,
  orquestracao ou tarefas nao comparaveis.

Correcao recomendada:
- Definir criterio por tipo:
  - trace lento: duracao total acima do threshold do produto;
  - chamada LLM lenta: span `llm_call` acima do threshold;
  - retrieval lento: span `retrieval` acima do threshold.
- Expor filtros separados ou mudar o nome da aba para "Traces > 2s".
- Ideal: backend aceitar `slow_kind=trace|llm|retrieval` e retornar motivo.

Definition of done:
- Orchestrator nao aparece como chamada lenta sem motivo explicito.
- Cada item lento mostra qual duracao disparou o alerta.

### Aba "RAG" usa heuristica estreita e pode misturar chamadas

Evidencia:
- `apps/web/app/o/[org]/p/[project]/traces/page.tsx` envia `rag=true`.
- `apps/api/app/api/routes.py` filtra RAG por `Trace.name ilike "rag.%"` ou
  `metadata.is_rag in ("true", "1")`.
- `apps/web/lib/rag.ts` detecta RAG no detalhe por spans como `rag.retrieve`,
  `rag.grounding.validate` e metadados de pipeline.

Impacto:
- Lista e detalhe podem usar criterios diferentes.
- Se todo o fluxo tiver metadata RAG no trace raiz, chamadas de orchestrator
  podem parecer "RAG" mesmo quando nao sao retrieval/grounding.

Correcao recomendada:
- Unificar contrato de RAG entre backend e frontend.
- Backend deve classificar RAG por existencia de span RAG/retrieval, metadata
  de pipeline ou campo canonico `metadata.is_rag`.
- Na lista, separar "Trace RAG" de "Span RAG" e mostrar o motivo.

Definition of done:
- A aba RAG lista apenas traces com evidencia RAG real.
- O detalhe e a lista concordam no mesmo criterio.
- Orchestrator aparece como parte do trace, nao como chamada RAG individual.

## P1 - Acoes principais ausentes ou parciais

### Criar outros projetos dentro do workspace

Evidencia:
- Backend ja tem `POST /projects` com `ProjectCreate`.
- Frontend tem `getProjects` e `patchProject`, mas nao tem `createProject`.
- `Sidebar` mostra `Workspace - {org}` e `{project}` como link para o projeto
  atual, sem menu/modal para criar ou trocar projeto.
- `EvoTopbar` carrega projetos para `WorkspaceSwitcher`, mas a UX nao oferece
  criacao de novo projeto.

Impacto:
- O produto prende o usuario no projeto default.
- Usuarios que separam agentes por produto, cliente ou pipeline de IA nao tem
  fluxo natural para criar novos projetos.

Correcao recomendada:
- Adicionar `createProject` em `apps/web/lib/api.ts`.
- Adicionar `createProjectAction` em `apps/web/lib/actions.ts`.
- Transformar o bloco de workspace/sidebar em menu com:
  - lista de projetos da org;
  - acao "Novo projeto";
  - form com nome, slug, descricao e ambiente default;
  - redirect para `/o/{org}/p/{novo_slug}` apos criar.

Definition of done:
- Usuario cria segundo projeto pela UI sem usar API manual.
- Projeto novo aparece no switcher imediatamente.
- Slug duplicado mostra erro legivel.

### Excluir chave API revogada esta parcial na branch atual

Evidencia:
- Alteracoes locais adicionam `DELETE /projects/{project_id}/api-keys/{key_id}`.
- `api_key_service.delete_key` impede apagar chave ativa e exige revogacao.
- `deleteApiKey` e `deleteApiKeyAction` existem no front local.
- A tabela de keys ainda mostra `-` para chaves revogadas, sem form/botao de
  exclusao.
- Nao ha teste encontrado para `deleteApiKeyAction`, `api_key_not_revoked` ou
  `DELETE /api-keys`.

Impacto:
- A intencao do Claude ficou incompleta: backend/action existem, mas o usuario
  nao tem interacao final para apagar chave revogada.

Correcao recomendada:
- Em chaves revogadas, renderizar botao "Excluir" com confirmacao.
- Manter 409 para chave ativa.
- Adicionar testes:
  - backend: DELETE revogada retorna 204 e some da listagem;
  - backend: DELETE ativa retorna 409;
  - frontend source test: chaves revogadas renderizam `deleteApiKeyAction`.

Definition of done:
- Chave ativa so pode ser revogada.
- Chave revogada pode ser excluida.
- A exclusao aparece na UI e atualiza a tabela.

### Notificacoes nao podem ser marcadas como lidas

Evidencia:
- Backend tem `/projects/{id}/notifications/mark-read`.
- `markNotificationsReadAction` existe.
- `NotificationsBell` so abre o dropdown e mostra "nao lida".

Impacto:
- Badge de notificacao pode ficar preso sem acao do usuario.

Correcao recomendada:
- Passar `project_id` e `current_path` ao sino.
- Adicionar botao "Marcar lidas" com ids unread.

Definition of done:
- Clicar marca unread como read e remove badge apos revalidacao.

### Seletor de ambiente do topbar e apenas estado local

Evidencia:
- `EvoTopbar` alterna `prod/staging/dev` com `useState`.
- `setEnvironmentAction` existe, mas nao e usada.
- Cookie `evalops_env` e escrito pela action, mas nao lido pelas paginas.

Impacto:
- Usuario acha que mudou o ambiente global, mas os dados nao mudam.

Correcao recomendada:
- Preferir URL query `?environment=` para manter navegacao previsivel.
- Alternativa: ler cookie no shell/paginas e aplicar nos fetches.

Definition of done:
- Ambiente escolhido altera as queries visiveis.
- Refresh e navegacao preservam o ambiente.

## P2 - Dados reais, mas incompletos ou pouco confiaveis

### Interacao real com valor e tokens

Evidencia:
- Ingestao soma `tokens_in`, `tokens_out` e `cost_usd` a partir dos spans.
- Se `cost_usd` nao vem no span, backend calcula por tabela de precos.
- `compute_cost_usd` retorna zero para provider/model ausente da tabela.
- UI de traces mostra tokens e custo total, mas nao deixa claro se o valor e
  real, estimado ou zero por modelo desconhecido.

Impacto:
- Usuarios podem interpretar custo zero como custo real.
- Modelos fora da tabela ficam invisiveis financeiramente.

Correcao recomendada:
- Persistir origem do custo: `provided`, `priced`, `estimated`, `unknown`.
- Mostrar badge/tooltip junto do valor.
- Expandir tabela de precos ou configurar precos por org/projeto.
- Para spans sem tokens reais, estimar tokens e marcar como estimado, sem
  apresentar como medicao real.

Definition of done:
- Cada custo exibido tem origem clara.
- Provider/model desconhecido nao parece gratis por acidente.

### Tamanho de export sempre vazio

Evidencia:
- Pagina de exports renderiza tamanho como `-`.
- `ExportJobOut` e `ExportJob` nao possuem `file_size_bytes`.

Impacto:
- Download funciona, mas tabela parece incompleta.

Correcao recomendada:
- Salvar `file_size_bytes` quando export termina.
- Exibir tamanho formatado.

Definition of done:
- Export completo mostra tamanho real do arquivo.

### Status linka rota inexistente no front

Evidencia:
- Footer do overview aponta para `/health`.
- Backend tem `/health/liveness` e `/health/readiness`.
- Nao existe rota web `/health`.

Impacto:
- Botao/status de confianca leva a 404 ou pagina inexistente.

Correcao recomendada:
- Criar pagina `/health` no web consumindo readiness/liveness da API, ou linkar
  diretamente para a API configurada.
- Remover texto estatico "Sistemas operando" se nao houver check real.

Definition of done:
- Status abre uma pagina valida e reflete saude real.

## P3 - Copy e promessas da UI

### "Criar experimento A/B" so navega

Evidencia:
- A sugestao do overview tem titulo "Criar experimento A/B", mas o row apenas
  linka para `/experiments`.

Impacto:
- Copy promete criacao, interacao entrega navegacao.

Correcao recomendada:
- Ou renomear para "Abrir experimentos";
- Ou abrir modal de criacao com contexto preenchido.

Definition of done:
- O verbo do botao corresponde ao que acontece.

### "Exportar dataset" aparece como acao indisponivel

Evidencia:
- Datasets tem botao disabled "Exportar dataset" e texto dizendo que o backend
  nao expoe endpoint.

Impacto:
- E honesto, mas polui a tela com uma acao que o usuario nao pode usar.

Correcao recomendada:
- Implementar endpoint de export de dataset, ou remover o card ate existir.

Definition of done:
- Nao ha botao visualmente acionavel para funcionalidade inexistente.

## Sequencia sugerida de implementacao

1. Corrigir `window` do overview com cutoff real no backend.
2. Corrigir classificacao de "Lentas" e "RAG" com motivo explicito.
3. Finalizar exclusao de API key revogada e testes.
4. Adicionar criacao de projetos pelo workspace/sidebar.
5. Conectar notificacoes e ambiente a actions reais.
6. Melhorar custo/tokens com origem do valor.
7. Corrigir status, tamanho de exports e copy de experimentos/datasets.

## Fora de escopo deste documento

- Redesign visual amplo.
- Refatoracao de arquitetura sem relacao com esses fluxos.
- Restaurar documentacao antiga removida.
