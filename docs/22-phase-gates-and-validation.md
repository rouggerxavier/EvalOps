# 22 - Phase Gates and Validation

Gates formais para decidir se o trabalho pode avancar para a proxima fase.
Cada gate existe para evitar dois problemas classicos:

1. overengineering cedo demais;
2. seguir adiante com uma base fraca e pagar a conta depois.

## 1. Como usar este documento

- Nao avancar de fase so porque o codigo "parece pronto".
- Cada gate precisa de evidencia objetiva.
- Se um gate falhar, o backlog da fase seguinte nao abre.

## 2. Gate 0 - Foundation ready

Objetivo:
confirmar que ambiente e base do repositorio suportam iteracao rapida.

Evidencias minimas:
- repositorio estruturado;
- CI minima passando;
- Docker Compose funcional;
- env vars documentadas;
- auth spike sem bloqueio estrutural.

Nao avancar se:
- API e web nao sobem localmente;
- deploy preview nao existe;
- estrategia de repo ainda esta em aberto.

## 3. Gate 1 - Tenancy and access ready

Objetivo:
garantir que dados futuros vao nascer com isolamento correto.

Evidencias minimas:
- login real funcionando;
- create org/project/key funcionando;
- key revocation funcionando;
- teste de isolamento multi-tenant cobrindo ao menos traces/projetos.

Nao avancar se:
- cross-tenant read ainda e possivel;
- key aparece em claro fora do create response;
- revogacao depende de restart/manual cache clear.

## 4. Gate 2 - Ingestion contract frozen

Objetivo:
congelar o shape do payload publico cedo, para nao quebrar SDK e apps reais.

Evidencias minimas:
- `POST /v1/traces` persistindo;
- idempotencia provada em teste;
- trace detail read path funcional;
- pricing/cost logic minima;
- example payloads continuam compativeis.

Nao avancar se:
- payload wire ainda muda de forma breaking;
- trace detail nao renderiza tool call/fallback;
- SDK nao consegue enviar traces reais.

## 5. Gate 3 - Trace UX useful

Objetivo:
provar que tracing isoladamente ja gera insight.

Evidencias minimas:
- overview com KPIs;
- listagem com filtros;
- detail com span tree;
- pelo menos um projeto real instrumentado.

Nao avancar se:
- o autor ainda nao consegue investigar um trace problematico pelo produto;
- a UX depende de consultar DB manualmente.

## 6. Gate 4 - Eval engine trustworthy

Objetivo:
introduzir avaliacao sem comprometer ingestao nem reproducibilidade.

Evidencias minimas:
- parser/validator YAML estavel;
- 7 evaluators MVP disponiveis;
- `POST /v1/evaluations/run` funcional;
- rubric versioning imutavel;
- judge path com output schema strict.

Nao avancar se:
- rubrica ainda exige decisao estrutural nao resolvida;
- trace detail nao mostra resultado de run;
- budget/cost caps nao existem.

## 7. Gate 5 - Regression path operational

Objetivo:
garantir que eval ja serve para decisao de engenharia.

Evidencias minimas:
- prompts versionados;
- datasets criaveis;
- experiments rodando;
- CLI regression com exit code correto;
- output legivel para CI e PR.

Nao avancar se:
- nao e possivel comparar ao menos 2 variantes no mesmo dataset;
- CLI nao pode ser usada em automacao simples.

## 8. Gate 6 - Feedback loop closed

Objetivo:
fechar o ciclo de melhoria continua com feedback humano e export.

Evidencias minimas:
- feedback persistido;
- review path minimo;
- export JSONL valido;
- usage counters e quotas mockadas atualizando.

Nao avancar se:
- corrected response nao pode virar dado util;
- export ainda depende de copiar JSON manualmente.

## 9. Gate 7 - MVP releasable

Objetivo:
declarar o MVP como algo que pode ser mostrado sem desculpas.

Evidencias minimas:
- checklist do `21` completo;
- deploy estavel;
- dados reais no produto;
- README, docs e demo prontos.

Nao avancar para 1.1 se:
- o MVP ainda nao esta apresentavel;
- a base sync ainda nao esta confiavel.

## 10. Gate 8 - Async hardening justified

Objetivo:
garantir que Arq/Redis entra por necessidade real, nao por ansiedade.

Evidencias minimas:
- fluxo sync/manual MVP completo;
- dor real de latencia ou throughput documentada;
- interfaces de EvalService/ExportService estabilizadas;
- modelo de fila e deduplicacao definido.

Nao iniciar 1.1 se:
- o problema principal ainda e corretude funcional;
- nao existe baseline p95 do ingestion para comparar antes/depois.

## 11. Matriz de validacao

| Gate | Owner principal | Evidencia tecnica | Evidencia de produto |
|---|---|---|---|
| 0 | infra/foundation | CI + compose + preview | n/a |
| 1 | auth/access | tests multi-tenant + key hashing | onboarding funcional |
| 2 | tracing | ingestion + idempotencia + totals | traces reais aparecem |
| 3 | web/traces | read-side queries + UI tests | investigacao de trace e util |
| 4 | eval | parser + evaluators + run tests | score aparece no trace |
| 5 | experiments/cli | CLI + experiment tests | regression demonstravel |
| 6 | feedback/export | JSONL valid + counters | ciclo de melhoria fecha |
| 7 | release | hosted smoke + docs | demo de portfolio pronta |
| 8 | async hardening | queue tests + perf delta | auto-eval nao degrada UX |

## 12. Regra de rollback de fase

Se uma fase avancou e uma validacao critica da fase anterior quebra depois:

1. parar trabalho novo;
2. restaurar conformidade do gate quebrado;
3. so entao retomar backlog seguinte.
