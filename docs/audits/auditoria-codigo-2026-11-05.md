# Auditoria de código — EvalOps (2026-11-05)

Base: `main` em `1141b80`, idêntica a `origin/main` (0 à frente, 0 atrás).
PR aberto: [rouggerxavier/EvalOps#19](https://github.com/rouggerxavier/EvalOps/pull/19) (rascunho, Quality Gate, não entra nesta base).

Método: leitura do código e execução real numa cópia exportada. Rodei API com uvicorn, SDK real,
Postgres 16 temporário e o agente da Grankasa só por leitura. Nenhum arquivo do projeto foi alterado
além deste relatório. "Provado" significa que o comportamento foi observado em execução;
"leitura" significa que a conclusão vem só do código. Caminhos de backend são relativos a `apps/api/app`;
`tracer.py` e `uploader.py` ficam em `packages/sdk-python/evalops`.

## Veredito

**Não conecte a Grankasa ainda: hoje o EvalOps aprova resposta ruim.** Um trace enviado pelo SDK, com a
fala `Apartamento garantido por R$ 999.999, sem nenhuma fonte.`, passou com score 1.0 numa rubrica que
proíbe `R$`. A mesma fala, enviada por ingestão crua, reprovou com 0.5. Medir com isso é pior do que não
medir, porque dá confiança falsa.

A base é aproveitável. Isolamento entre tenants, ingestão e autenticação de chave resistiram aos testes.
O problema está no elo SDK → avaliador → métrica e em duas falhas de implantação.

## Status

Os P0 (itens 1 a 9) foram corrigidos na branch `fix/p0-auditoria`. Validação: 354 testes API, 35 testes
SDK em Python 3.9 e 3.12, as provas de execução repetidas e os dois compose subindo de verdade com Postgres, com
`readiness` 200. Na stack de produção, migration chegou ao head, o export baixou com 200 e
`set_org_limits.py` mudou a cota.

Limites das correções:

- Erro permanente 4xx (chave errada, cota esgotada): o lote é descartado com aviso, sem dead-letter, conforme
  o contrato já documentado no SDK.
- Um trace inválido num lote derruba o lote inteiro com 422.
- Banco com Alembic já em `0007_evaluation_runs_trace_created_index` precisa de
  `alembic stamp 0007_eval_runs_trace_created`. Só SQLite pode estar nesse estado.
- O job `migrate-postgres` foi adicionado à CI, mas não rodou: depende do GitHub Actions.

Os P1 (itens 10 a 24) também foram corrigidos na mesma branch. Validação:

- 403 testes API em SQLite, 36 testes SDK em Python 3.9 e 3.12, 145 testes web, typecheck e build.
- Em Postgres 16, os testes de regressão de P0 e P1 passaram. O restante da suíte rodou com as FKs desligadas,
  porque 34 testes antigos inserem linhas fora de ordem e só passam em SQLite. Nenhum erro de SQL do app apareceu.
- Na stack de produção (Postgres, Redis, worker), o lote enfileirou 4 traces e o relatório devolveu 2 aprovados,
  1 reprovado e 1 erro. Reenviar o lote só reenfileirou o erro. Chave sem escopo `evaluate` recebeu 403.
- Item 21 medido em Postgres com juiz de 4 s: ingestão durante a avaliação caiu de 3,73 s para 0,09 s.
- Telas de Experimentos, Traces, Avaliações e Overview conferidas no navegador, com dados descartáveis.

A conferência das telas achou dois defeitos, já corrigidos: juiz sem chave cobrava o custo estimado sem chamar
nada, e a tabela de Avaliações mostrava score 1,00 de um run em que o juiz não rodou.

Limites das correções:

- O custo do juiz é uma estimativa. Modelo sem preço na tabela usa a taxa padrão e pode bater no `cost_cap_usd`
  padrão de 0,01 em prompts longos. Nesse caso, defina `cost_cap_usd` na rubrica.
- Não há avaliação automática na ingestão nem amostragem: só lote, limitado por `limit`.
- `ignored_fields` e o relatório por rubrica existem só na API. Chave com escopo `evaluate` só é criada via API.
- Experimentos continuam sintéticos e ignoram flags. A tela agora avisa; o item 16 só fecha ao importar resultados
  do harness.
- Nenhuma chamada real a LLM foi feita. O roteamento por provider foi testado com HTTP simulado.
- O PR #19 toca `eval_service.py` e precisa de rebase sobre esta branch.

## P0 — Bloqueiam a conexão

| # | Achado | Onde | Evidência |
|---|---|---|---|
| 1 | **Injeção de template: execução de código e leitura de segredos no servidor.** Qualquer conta registrada cria rubrica com Jinja sem sandbox. O registro é aberto. Com `JWT_SECRET` lido, dá para forjar token de qualquer usuário de qualquer organização. | `domain/evaluators/exact_match.py:32`, `llm_judge.py:46`, `cosine_similarity.py:62`, `domain/services/experiment_service.py:39` | Provado: `raw_output.expected` devolveu o segredo falso e o resultado de `id -un` |
| 2 | **Mensagem de cliente vira template no replay.** Com `rerun_variables` preenchido, o conteúdo de `messages_in` é renderizado sem sandbox. Um texto enviado no WhatsApp executaria código no worker. | `workers/replay_worker.py:81` | Provado na função `_render`; fluxo completo por leitura |
| 3 | **SDK não envia a resposta onde o avaliador lê.** `resolver.py` só olha `messages_out` e `metadata.output`; o SDK só oferece `set_io`, que grava em `span.output`. O avaliador recebe texto vazio. | `domain/rubrics/resolver.py:47`, `packages/sdk-python/evalops/tracer.py:50`, `:99` | Provado: 1.0 aprovado (SDK) contra 0.5 reprovado (controle) |
| 4 | **SDK não envia modelo, provider, tokens nem custo.** Não há API para isso. `instrument_openai` grava só o nome da classe da resposta. | `tracer.py:50`, `evalops/__init__.py:91` | Provado: todos `null`, custo 0 |
| 5 | **Migrations quebram no Postgres.** O id `0007_evaluation_runs_trace_created_index` tem 40 caracteres e `alembic_version` aceita 32. O job `migrate` falha e a API de produção não sobe. | `apps/api/alembic/versions/0007_*.py`, `docker-compose.prod.yml` | Provado: `StringDataRightTruncation`. Alargando a coluna, chega ao head |
| 6 | **Uploader entra em laço de ~100 req/s em erro permanente** (401, 402, 422): nunca para, nunca grava dead-letter. `environment="production"` já causa 422, porque a API só aceita `dev\|staging\|prod` e o SDK não valida. Em 5xx repete para sempre, sem dead-letter enquanto roda. | `uploader.py:305`, `:315` | Provado: 690–714 requisições em 7 s, 0 dead-letters |
| 7 | **Cota fixa de 1000 traces e 500 avaliações por mês, sem como mudar.** Só existe o plano `free` e nenhuma rota altera plano. Ao estourar, a API responde 402 e o item 6 dispara. | `domain/services/usage_service.py:29` | Provado no default; ausência de rota por busca |
| 8 | **Download de export falha** com as dependências atuais: `main.py` repete `http.request` em vez de `http.disconnect`. Sem lockfile Python, instalação nova já traz isso. São as 3 falhas da suíte. | `main.py:104` | Provado em uvicorn: `RemoteProtocolError`, 3 testes vermelhos |
| 9 | **`docker-compose.yml` e `.env.example` não sobem:** URL é reescrita para `psycopg`, que não está no `pyproject.toml`. | `db.py`, `apps/api/pyproject.toml` | Provado: `ModuleNotFoundError: No module named 'psycopg'` |

## P1 — A métrica mente ou não existe

| # | Achado | Onde | Evidência |
|---|---|---|---|
| 10 | **Texto vazio passa.** `must_not_match`, `require: none` e `length_bounds` só com `max` aprovam vazio. Vale também para trace com redação ligada, que apaga o conteúdo. | `domain/evaluators/*` | Provado |
| 11 | **Erro de digitação no alvo passa.** `trace.outptu.txet` é aceito e vira texto vazio; o parser não valida `config`. | `resolver.py:72`, `:78`, `domain/rubrics/parser.py` | Provado: `passed: true` |
| 12 | **Resposta final pode ser ignorada.** Se o último `llm_call` só tem `tool_calls`, a saída fica vazia e aprova. Os spans vêm sem `order_by`, então "último" depende do banco. | `resolver.py:47`, `domain/services/eval_service.py:146` | Provado no vazio; ordem por leitura |
| 13 | **Falha crítica declarada é ignorada.** `automatic_fail_conditions` com `flag` não tem executor. `criteria`, `judge`, `cost_limits`, `thresholds` e `output_schema` também são aceitos e não fazem nada. | `eval_service.py:284` | Provado: `auto_fail` e `passed: true` |
| 14 | **Falha de infraestrutura vira nota de qualidade.** Juiz fora do ar conta como 0 e o run sai `completed`, reprovado. Juiz sem campo `score` vira 0 sem nenhum erro. | `eval_service.py:273`, `llm_judge.py:153` | Provado |
| 15 | **Run com erro nunca mais é reavaliado** naquela versão: responde 409. Exige publicar outra versão da rubrica. | `api/routes_evaluations.py:80` | Provado |
| 16 | **Experimentos são falsos.** Nenhum modelo é chamado: a "saída" é o template renderizado mais `[model=... params=...]`. A tela não avisa. Comparar variantes aqui não mede o agente. | `experiment_service.py:146` | Provado |
| 17 | **"Score médio" do overview é sempre vazio:** `avg_score` está fixo em `None`. | `api/routes.py:844`, `:913`, `web/.../page.tsx:199` | Provado com 9 runs existentes |
| 18 | **Custo errado.** Tabela com 5 modelos e busca exata. `openai/gpt-6-luna` via `openrouter` dá custo 0 rotulado `estimated`. Os preços da tabela precisam ser conferidos. | `infra/llm/pricing.py:5`, `trace_ingest_service.py:147` | Provado no custo 0 |
| 19 | **Juiz preso à OpenAI.** Prefixo do modelo é descartado: `gemini/gemini-2.5-flash` vai para `api.openai.com`. `OPENAI_API_KEY` não está no `.env.example` nem no compose de produção. A Grankasa usa OpenRouter. | `llm_judge.py:30` | Provado |
| 20 | **Orçamento do juiz furado.** O gasto soma por projeto e o limite é da organização. Retentativa só conta a última chamada. Experimentos não entram na conta. | `eval_service.py:49`, `:61`, `llm_judge.py:163` | Retentativa provada; resto por leitura |
| 21 | **Avaliação segura a ingestão inteira da organização (Postgres).** O `FOR UPDATE` no contador é tomado antes das chamadas ao juiz (timeout de 60 s cada) e só é solto no commit. | `routes_evaluations.py:108` | Leitura; não executado |
| 22 | **Sem avaliação automática.** Uma rota, um trace por vez, com JWT de usuário. A chave de API só serve para `POST /traces`; o escopo `read` é decorativo. Não há lote, amostragem ou CI. | `deps.py:78`, `api/routes.py:469` | Busca no código |
| 23 | **Sem conceito de conversa, nem tendência.** Trace é um turno e não há `conversation_id`. O SDK não define metadata, `user_ref` ou prompt por trace. Não há série de score por versão de rubrica nem medida de variância do juiz. | `models.py`, `tracer.py` | Busca no código |
| 24 | **Sinais inventados.** Nada grava `Notification`, então o sino nunca toca. A causa exibida pode ser chute, como `vector_db_timeout` e `low_confidence`. | `api/routes.py:334`, `:338` | Busca no código |

## P2 — Robustez

- **SDK async:** `@evalops.trace` em `async def` fecha o trace antes de rodar: duração 0, spans perdidos, saída `<coroutine object>`. Provado. Não atinge `run_minimal_turn`, que é síncrono.
- **SDK bloqueia o chamador:** com a fila cheia, o envio vira síncrono com retentativas, cerca de 15 s por turno com a API fora. Risco real para o lease do worker da Grankasa. Leitura (`uploader.py:260`).
- **SDK perde dados:** sem `atexit` e sem `shutdown` público (provado); `errors[]` em resposta 202 é ignorado, então o trace ruim some em silêncio (`uploader.py:166`, provado).
- **Replay:** enfileira antes do commit e pode não achar o trace; fica `queued` para sempre sem worker; não consome orçamento; só fala com OpenAI (`routes_trace_actions.py:433`, leitura).
- **Juiz:** o texto do trace entra no prompt sem delimitação, abrindo injeção contra a nota. Se o template falha, o juiz recebe o template cru (`llm_judge.py:46`, leitura).
- **`regex_match`:** regex do usuário roda sem limite de tempo (ReDoS, leitura).
- **`client_trace_id` opcional:** sem ele, retentativa duplica o trace (provado).
- **Redação é tudo ou nada:** ou guarda o texto integral, ou apaga tudo e não dá para avaliar. Não há mascaramento.
- **Dependências:** `npm audit --omit=dev` aponta `next` como crítico e 4 pacotes transitivos como altos (nanoid, postcss, sharp, source-map-js). Corrigido na branch `fix/web-deps-audit`: `next` 15.5.29 e override de `postcss` 8.5.32; `npm audit --omit=dev` zerado.
- **Lockfile web fora de sincronia:** `npm ci` falha por faltar Playwright; a CI usa `npm install` e esconde isso. Corrigido na branch `fix/web-deps-audit`: lockfile regenerado, `npm ci` limpo passa.
- **Sem lockfile Python:** faixas abertas (`fastapi>=0.115,<1`) causaram o item 8. Já resolvido: `apps/api/requirements.lock` (`uv pip compile`, inclui `dev`) fixa todas as dependências instaladas; CI, os dois compose e o README instalam com `-c requirements.lock`. Não há Dockerfile da API.
- **Limpeza:** `maintenance.run_all` não tem agendamento em compose nem worker.
- **Papéis:** nenhuma rota verifica papel, só pertencimento. Hoje não há convite, então o risco é baixo; vira real no dia em que houver.
- **`alembic check`:** acusa 3 índices criados por migration e ausentes dos models; `create_all` fica sem eles. Corrigido na branch `claude/schema-docs-902ced`: `ix_evaluation_runs_trace_created` e os dois `ix_traces_metadata_prompt_*` (só Postgres, via `ddl_if`) declarados em `app/models.py`; `alembic check` em Postgres 16 dá `No new upgrade operations detected.`
- **Docs:** o README cita `docs/04-*`, `docs/07-*`, `docs/11-*` e `docs/plans/`, que não existem, e Next 14 (é 15.5.18). O código cita `docs/ops/database-migrations.md`, também ausente. Corrigido na branch `claude/schema-docs-902ced`: README sem links quebrados e com Next.js 15; `docs/ops/database-migrations.md` criado com o fluxo real. Resta `apps/web/lib/rag.ts` citando `docs/08-*`, fora do escopo.

## Por que os testes não pegaram

Suíte API: 335 de 338 passam, 92% de cobertura. SDK: 26 de 26. Web: 145 de 145, typecheck e build ok.
A cobertura é alta e não testa o que importa:

- `apps/api/tests/conftest.py` força SQLite, então o bug de migration é invisível.
- Testes de avaliador montam `messages_out` à mão. Nenhum teste faz SDK → API → avaliação.
- A CI da `main` não roda os testes web, e o último run na `main` é de maio.

## O que está bom

- **Isolamento entre tenants:** 16 leituras e 3 escritas de outro usuário, em Postgres, todas com 404.
- **API em Postgres:** as 16 rotas de leitura exercitadas responderam 200, depois de contornar o item 5.
- **Ingestão:** p50 de 19,7 ms por POST em SQLite, com argon2 por requisição.
- **Chaves e erros:** chave com hash argon2, limite de corpo, `safe_errors` e auditoria.
- **Quality Gate (PR #19):** o desenho é bom, porque evidência ausente pede revisão em vez de aprovar.

Limites do PR #19, a resolver antes do merge:

- Herda o item 3: texto vazio aprova.
- Exige todos os traces avaliados; sem o item 22, fica em "revisão" para sempre em volume real.
- Custo desconhecido entra como 0 e passa no limite.

## Como conectar a Grankasa depois dos P0

O ponto de encaixe já existe e não exige mexer no prompt nem no agente.

1. **Adaptador:** um decorator da porta `ChatModel` (`backend/application/minimal_agent.py`), envolvendo `OpenRouterToolChat`. A porta já entrega mensagens, chamadas de ferramenta e `usage` com `prompt`, `completion` e `cost_usd`. O custo real da OpenRouter chega como `provided`, sem depender da tabela.
2. **Só dados sintéticos primeiro:** rodar sobre `backend/evals/conversation_quality` e `conversation_e0`, com envio falso. A Grankasa proíbe nome de cliente, JID e fatos de imóvel em log, e o SDK hoje grava `repr` dos argumentos (`tracer.py:169`). Conversa real exige mascaramento antes, e decidir se o texto pode ir ao provedor do juiz.
3. **Papel de cada lado:** a Grankasa já tem regressão pareada com juiz cego (`run_paired`, `judge.py`), melhor que os experimentos daqui. O EvalOps deve guardar os resultados, mostrar tendência e aplicar o gate, sem duplicar esse harness.
4. **Custo:** o README do E0 registra avaliação paga suspensa por falta de saldo em 2026-10-08. O juiz precisa de orçamento aprovado.

## Ordem sugerida

1. **Segurança (1, 2):** `ImmutableSandboxedEnvironment` nos avaliadores; replay sem renderizar conteúdo como template.
2. **Implantação (5, 8, 9):** encurtar o id da 0007, corrigir `_receive`, adicionar `psycopg`, gerar lockfile e um job de CI em Postgres.
3. **SDK (3, 4, 6):** `set_llm(...)` com modelo, tokens, custo e mensagens; validar `environment`; parar em 4xx; dead-letter; `shutdown`. Um teste SDK → API → avaliação como trava.
4. **Validade da nota (10–15, 19):** saída vazia vira `error`; validar `config`; separar erro de reprovação; permitir reavaliar; juiz configurável com OpenRouter.
5. **Métrica (17, 18, 22, 23):** `avg_score` real, avaliação em lote, `conversation_id`, tendência por versão. Cota configurável (7). Integrar o PR #19.
6. **Grankasa:** adaptador e primeira bateria sintética. Critério de pronto: reprovar a fala com preço inventado e aprovar a correta, nos mesmos cenários, duas rodadas seguidas.
7. **Experimentos (16):** avisar na tela já na etapa 4; depois trocar por resultados importados do harness.

## Não verificado

- Fluxo completo de replay com Redis e worker não foi rodado.
- Telas do dashboard fora das quatro alteradas não foram testadas no navegador.
- Carga e volume de produção não foram medidos.
- Nenhuma chamada real a LLM foi feita; o juiz foi simulado.
