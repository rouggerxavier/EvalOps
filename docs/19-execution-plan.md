# 19 - Execution Plan

Este documento traduz a spec do EvalOps Studio em um plano de execucao
realista, faseado e implementavel. Ele complementa
[`14-implementation-roadmap.md`](14-implementation-roadmap.md): o `14` continua
como roadmap macro; este `19` define ordem, dependencias, validacoes e limites
de escopo.

## 1. Objetivo

Entregar um MVP que prove, com dados reais, que o autor sabe:

- construir plataforma multi-tenant com auth real e API keys seguras;
- ingerir traces de LLM/agentes com bom schema e boa DX;
- avaliar respostas com rubricas YAML + heuristicas + LLM-as-judge;
- rodar comparacoes e regressao sem acoplar ingestion a avaliacao;
- expor valor em dashboard e exportar dataset util.

## 2. Principios operacionais

1. `POST /v1/traces` e o hot path e precisa estabilizar cedo.
2. O MVP continua sync/manual; a arquitetura nasce async-ready.
3. Schema futuro-proof, implementacao presente-minima.
4. Toda fase precisa gerar algo visivel ou testavel.
5. Depois da estabilizacao de ingestion, mudancas breaking em payload publico
   ficam proibidas no MVP.

## 3. Sequencia oficial de implementacao

### Fase 0 - Foundation

Objetivo:
preparar repositorio, tooling, compose, CI e auth spike.

Entregaveis:
- estrutura de repositorio;
- scaffolding `apps/api`, `apps/web`, `packages/sdk-python`;
- Docker Compose local;
- CI minima;
- env vars documentadas;
- spike Auth.js v5 em preview.

Validacao:
- `docker compose up` sobe web/api/postgres/redis;
- CI roda sem configuracao manual fora de secrets.

### Fase 1 - Identity, tenancy and access

Objetivo:
fechar autenticacao, organizations, projects e API keys antes de expor dados.

Entregaveis:
- tabelas identity/access;
- login -> org -> project;
- criacao/revogacao de API key;
- enforcement de `organization_id` no backend.

Validacao:
- usuario novo cria projeto e key sem ajuda;
- key revogada para de funcionar;
- tenant A nao le tenant B.

### Fase 2 - Trace ingestion and SDK

Objetivo:
fechar o hot path e estabilizar o contrato publico principal.

Entregaveis:
- migrations `traces`, `spans`, `events`;
- `POST /v1/traces` batch e idempotente;
- calculo de custo na ingestion;
- listagem e detalhe de traces;
- SDK Python `init`, `@trace`, `span()`.

Validacao:
- mesmo `client_trace_id` nao duplica;
- trace detail traz spans e events;
- SDK envia traces reais em uma app de exemplo.

### Fase 3 - Dashboard MVP for traces

Objetivo:
provar valor do tracing antes de complicar com eval.

Entregaveis:
- project overview;
- trace list com filtros;
- trace detail com arvore de spans;
- empty states com snippet de instrumentacao.

Validacao:
- o autor consegue investigar um trace problematico pelo produto;
- pelo menos um projeto real ja aparece com dados.

### Fase 4 - Rubrics and sync evaluation engine

Objetivo:
entregar avaliacao sem comprometer ingestion.

Entregaveis:
- parser/validator de YAML;
- migrations evaluation;
- 7 evaluators MVP;
- `POST /v1/evaluations/run` sincronico;
- runs no detalhe do trace.

Validacao:
- rubrica sobe em nova versao;
- trace real pode ser avaliado manualmente;
- falha de evaluator individual nao mata a run inteira.

### Fase 5 - Prompt versioning, datasets, experiments and regression

Objetivo:
transformar o motor de eval em mecanismo de decisao de engenharia.

Entregaveis:
- prompts/prompt_versions;
- datasets/dataset_items;
- experiments/experiment_runs;
- CLI para push e run;
- regression suite com exit code.

Validacao:
- experimento simples roda 1 dataset x 2 variantes;
- regression suite falha corretamente em cenario de regressao.

### Fase 6 - Feedback, export and mock quotas

Objetivo:
fechar o loop de melhoria continua e deixar o schema SaaS-ready.

Entregaveis:
- feedback endpoint + UI minima;
- export JSONL compativel com HF/chat fine-tuning;
- usage counters;
- quotas mockadas;
- audit log inicial.

Validacao:
- feedback aparece no trace;
- export gera JSONL valido;
- usage counters aumentam em ingestion e eval.

### Fase 7 - MVP hardening and portfolio release

Objetivo:
transformar um sistema funcional em um MVP apresentavel e reproduzivel.

Entregaveis:
- polish de UX;
- README e docs do SDK;
- deploy hosted estavel;
- dados reais de pelo menos 1 projeto;
- video e assets de portfolio.

Validacao:
- checklist do MVP aprovado;
- demo completa roda sem workaround manual.

### Fase 1.1 - Async hardening

Objetivo:
tirar workloads lentos do request path sem reabrir design estrutural.

Entregaveis:
- worker Arq;
- eval async;
- export async;
- cache de judge;
- rate limit Redis robusto.

Validacao:
- ingestion continua rapida com auto-eval ligado;
- fila sobrevive a retry e deduplicacao.

## 4. Escopo por horizonte

### MVP estrito

- auth real;
- multi-tenant real;
- API keys seguras;
- ingestion + SDK Python;
- dashboard traces;
- rubricas YAML;
- eval sincronico/manual;
- prompts, datasets, experiments, regression CLI;
- feedback + export JSONL;
- billing mockado;
- deploy reproducivel.

### Fase 1.1

- worker Redis/Arq;
- export async;
- cache de judge;
- auto-eval mais confiavel;
- hardening operacional.

### Pos-MVP imediato

- snapshots de dataset;
- compare trace vs trace;
- auto-instrument Gemini/Anthropic;
- webhooks;
- drift alerts basicos.

### Futuro

- Stripe real;
- RBAC granular;
- OTLP importer;
- TS SDK;
- ClickHouse hot path;
- SSO enterprise.

## 5. Dependencias criticas

| Item | Bloqueia | Observacao |
|---|---|---|
| Auth + org/project | tudo web/admin | sem contexto de tenant nao existe produto |
| API keys | SDK e ingestion | SDK sem key real e demo falsa |
| Trace schema | read path, eval, export | precisa estabilizar cedo |
| Rubric schema | eval, experiments, CLI | nao reabrir salvo bug real |
| Prompt version refs | experiments, reproducibilidade | pode nascer simples |
| Dataset shape | regression/export | formato padrao precisa fechar |
| Redis | Fase 1.1 | nao bloquear MVP por isso |

## 6. Estrategia anti-overengineering

1. Nao introduzir worker antes do fluxo sync/manual passar de ponta a ponta.
2. Nao construir builder visual de rubrica.
3. Nao suportar mais de 7 evaluators no MVP.
4. Nao otimizar com ClickHouse, particionamento ou OTLP nativo no corte inicial.
5. Nao criar SDK TS agora.
6. Nao construir auto-eval robusto em ingestion antes de validar uso manual.
7. Nao abrir varias integracoes de auth.

## 7. Pontos obrigatorios de validacao

- Gate A: tenancy e auth seguros antes de qualquer dado sensivel.
- Gate B: ingestion p95 aceitavel antes de ligar qualquer auto-eval.
- Gate C: trace detail util antes de investir pesado em eval.
- Gate D: rubrica e parser estaveis antes de experiments/regression.
- Gate E: CLI de regression funciona antes de polish de portfolio.
- Gate F: deploy e dados reais existem antes de declarar MVP done.
