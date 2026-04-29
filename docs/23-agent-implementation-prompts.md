# 23 - Agent Implementation Prompts

Prompts operacionais para usar com agentes de implementacao sem reexplicar o
projeto inteiro a cada fase.

## 1. Regras comuns

Use este prefixo em qualquer fase:

```txt
Voce esta implementando o projeto EvalOps Studio a partir dos specs em docs/.

Antes de alterar codigo:
- leia os documentos relevantes da fase atual;
- preserve as decisoes de ADR-0001 a ADR-0005;
- nao implemente nada fora do escopo da fase;
- nao reabra a discussao de worker async no MVP core;
- nao acople trace ingestion ao motor de avaliacao;
- mantenha multi-tenant + auth real desde o dia 1;
- billing continua mockado, mas o schema correto precisa ser respeitado;
- use FastAPI + Python 3.12 no backend, Next.js 15 no frontend e PostgreSQL 16;
- Redis/Arq so e obrigatorio na Fase 1.1.

Quando concluir:
- rode os testes relevantes;
- liste arquivos alterados;
- diga claramente o que ficou pendente e por que.
```

## 2. Prompt - Fase 0 Foundation

```txt
Implemente apenas a Fase 0 do EvalOps Studio.

Leia:
- docs/04-system-architecture.md
- docs/14-implementation-roadmap.md
- docs/15-testing-strategy.md
- docs/16-deployment-and-devops.md
- docs/decisions/ADR-0001-tech-stack.md

Objetivo:
- scaffolding de repositorio e ferramentas;
- Docker Compose local;
- CI minima;
- base de apps/api, apps/web e packages/sdk-python;
- sem implementar regras de negocio ainda.
```

## 3. Prompt - Fase 1 Identity and access

```txt
Implemente apenas identity, organizations, projects e API keys.

Leia:
- docs/01-product-requirements.md
- docs/03-mvp-scope.md
- docs/05-domain-model.md
- docs/06-data-model.md
- docs/07-api-spec.md
- docs/13-security-privacy-and-compliance.md
- docs/decisions/ADR-0005-auth-and-api-keys.md

Entregue:
- migrations identity/access;
- endpoints e services;
- UI minima onboarding/projetos/keys;
- testes de hashing, revogacao e isolamento.
```

## 4. Prompt - Fase 2 Tracing and SDK

```txt
Implemente apenas tracing core e SDK Python.

Leia:
- docs/03-mvp-scope.md
- docs/05-domain-model.md
- docs/06-data-model.md
- docs/07-api-spec.md
- docs/08-tracing-and-events-spec.md
- docs/examples/trace-ingestion-payload.json
- docs/decisions/ADR-0004-tracing-data-model.md

Entregue:
- migrations tracing;
- IngestionService;
- read path minimo para list/detail;
- pacote `evalops-python` com `init`, `@trace`, `span()`.

Nao faca:
- auto-eval acoplado ao request path;
- worker Redis;
- OTLP import.
```

## 5. Prompt - Fase 3 Dashboard traces

```txt
Implemente apenas a camada web necessaria para tornar traces navegaveis.

Leia:
- docs/11-dashboard-and-analytics.md
- docs/07-api-spec.md
- docs/08-tracing-and-events-spec.md
- docs/18-portfolio-positioning.md

Entregue:
- project overview;
- traces list;
- trace detail com arvore de spans;
- empty states que ensinam a instrumentar.
```

## 6. Prompt - Fase 4 Rubrics and sync eval

```txt
Implemente apenas rubricas YAML e avaliacao sincronica/manual.

Leia:
- docs/09-evaluation-engine-spec.md
- docs/07-api-spec.md
- docs/06-data-model.md
- docs/examples/evaluation-rubric-example.yaml
- docs/decisions/ADR-0002-mvp-scope.md
- docs/decisions/ADR-0003-evaluation-strategy.md

Entregue:
- migrations evaluation;
- eval engine;
- endpoints de rubrics/evaluations;
- UI minima para subir rubric e ver runs.

Nao faca:
- worker async;
- no-code rubric builder;
- custom Python evaluators.
```

## 7. Prompt - Fase 5 Prompts, datasets, experiments and regression

```txt
Implemente apenas prompts versionados, datasets, experiments e CLI de regression.

Leia:
- docs/10-prompt-and-model-versioning.md
- docs/12-human-feedback-and-datasets.md
- docs/07-api-spec.md
- docs/06-data-model.md
- docs/examples/regression-test-suite-example.json

Entregue:
- migrations correspondentes;
- services e endpoints;
- saida de regression com exit code e relatorio legivel.
```

## 8. Prompt - Fase 6 Feedback, export and usage

```txt
Implemente apenas feedback humano, export JSONL e quotas mockadas.

Leia:
- docs/12-human-feedback-and-datasets.md
- docs/13-security-privacy-and-compliance.md
- docs/07-api-spec.md
- docs/06-data-model.md
- docs/examples/human-feedback-example.json
- docs/examples/dataset-export-jsonl-example.jsonl

Entregue:
- migrations feedback/export/billing;
- endpoints;
- serializer JSONL;
- testes de export valido e contador de uso.
```

## 9. Prompt - Fase 7 MVP polish and release

```txt
Trabalhe apenas no hardening e polish do MVP.

Leia:
- docs/21-mvp-acceptance-checklist.md
- docs/18-portfolio-positioning.md
- docs/16-deployment-and-devops.md

Objetivo:
- fechar gaps do checklist;
- melhorar docs e empty states;
- garantir deploy estavel;
- preparar demo de portfolio.
```

## 10. Prompt - Fase 1.1 Async hardening

```txt
Implemente apenas a Fase 1.1: tirar workloads lentos do request path.

Leia:
- docs/19-execution-plan.md
- docs/22-phase-gates-and-validation.md
- docs/14-implementation-roadmap.md
- docs/16-deployment-and-devops.md
- docs/decisions/ADR-0001-tech-stack.md
- docs/decisions/ADR-0002-mvp-scope.md

Entregue:
- Arq worker;
- eval async;
- export async;
- cache de judge;
- rate limit Redis robusto.
```

## 11. Prompt - Review mode

```txt
Revise a implementacao do EvalOps Studio em modo code review.

Priorize:
- bugs e regressao funcional;
- violacoes de multi-tenancy;
- pontos em que ingestion foi acoplado indevidamente a avaliacao;
- inconsistencias com as specs em docs/;
- testes ausentes nas areas de maior risco.
```
