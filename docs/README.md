# EvalOps Studio - Documentation Index

Esta documentacao foi escrita em modo **Spec Driven Development**: o objetivo e
que qualquer engenheiro consiga ler os specs, entender o produto e implementar
o sistema sem ambiguidades criticas.

Cada documento marca explicitamente:

- **[MVP]** - requisito obrigatorio do MVP.
- **[Recomendado]** - recomendacao tecnica do autor da spec, com justificativa.
- **[Futuro]** - melhoria pos-MVP, fora de escopo agora.
- **[Decisao pendente]** - bloqueio que precisa de input humano.

## Mapa dos documentos

### Produto
| # | Documento | O que entrega |
|---|-----------|---------------|
| 00 | [Project Overview](00-project-overview.md) | Visao, problema, valor, posicionamento |
| 01 | [Product Requirements](01-product-requirements.md) | Requisitos funcionais e nao-funcionais |
| 02 | [Personas & Use Cases](02-user-personas-and-use-cases.md) | Quem usa, jornadas e casos de uso |
| 03 | [MVP Scope](03-mvp-scope.md) | O que entra/sai do MVP, criterios de aceite |
| 18 | [Portfolio Positioning](18-portfolio-positioning.md) | Como apresentar para recrutadores/clientes |

### Engenharia
| # | Documento | O que entrega |
|---|-----------|---------------|
| 04 | [System Architecture](04-system-architecture.md) | Componentes, diagramas, fluxos |
| 05 | [Domain Model](05-domain-model.md) | Entidades, agregados, regras de negocio |
| 06 | [Data Model](06-data-model.md) | Schemas SQL, indices, constraints |
| 07 | [API Specification](07-api-spec.md) | Endpoints REST, contratos, exemplos |
| 08 | [Tracing & Events Spec](08-tracing-and-events-spec.md) | Esquema de traces/spans/events |
| 09 | [Evaluation Engine Spec](09-evaluation-engine-spec.md) | Rubricas, evaluators, regression tests |
| 10 | [Prompt & Model Versioning](10-prompt-and-model-versioning.md) | Registry, semver, experiments |
| 11 | [Dashboard & Analytics](11-dashboard-and-analytics.md) | UX, telas, metricas, drill-down |
| 12 | [Human Feedback & Datasets](12-human-feedback-and-datasets.md) | HITL, anotacao, exportacao |
| 13 | [Security, Privacy & Compliance](13-security-privacy-and-compliance.md) | Auth, API keys, redaction, LGPD |

### Operacao
| # | Documento | O que entrega |
|---|-----------|---------------|
| 14 | [Implementation Roadmap](14-implementation-roadmap.md) | Fases, milestones, dependencias |
| 15 | [Testing Strategy](15-testing-strategy.md) | Piramide, eval-de-evals, contract tests |
| 16 | [Deployment & DevOps](16-deployment-and-devops.md) | CI/CD, environments, IaC |
| 17 | [Risks, Tradeoffs & Open Questions](17-risks-tradeoffs-and-open-questions.md) | Riscos, duvidas, decisoes pendentes |
| 19 | [Execution Plan](19-execution-plan.md) | Ordem real de execucao, dependencias e limites de escopo |
| 20 | [Implementation Task Breakdown](20-implementation-task-breakdown.md) | Breakdown por fase, arquivos provaveis, testes e aceite |
| 21 | [MVP Acceptance Checklist](21-mvp-acceptance-checklist.md) | Gate final para declarar o MVP pronto |
| 22 | [Phase Gates & Validation](22-phase-gates-and-validation.md) | Gates objetivos para avancar entre fases |
| 23 | [Agent Implementation Prompts](23-agent-implementation-prompts.md) | Prompts operacionais para agentes de implementacao |

### Decisoes arquiteturais (ADRs)
- [ADR-0001 - Tech Stack](decisions/ADR-0001-tech-stack.md)
- [ADR-0002 - MVP Scope](decisions/ADR-0002-mvp-scope.md)
- [ADR-0003 - Evaluation Strategy](decisions/ADR-0003-evaluation-strategy.md)
- [ADR-0004 - Tracing Data Model](decisions/ADR-0004-tracing-data-model.md)
- [ADR-0005 - Auth & API Keys](decisions/ADR-0005-auth-and-api-keys.md)

### Exemplos / artefatos
Payloads e fixtures sinteticos para referencia de API, SDK Python, seeds,
testes de regressao e export:

- [`examples/trace-ingestion-payload.json`](examples/trace-ingestion-payload.json)
- [`examples/evaluation-rubric-example.yaml`](examples/evaluation-rubric-example.yaml)
- [`examples/regression-test-suite-example.json`](examples/regression-test-suite-example.json)
- [`examples/human-feedback-example.json`](examples/human-feedback-example.json)
- [`examples/dataset-export-jsonl-example.jsonl`](examples/dataset-export-jsonl-example.jsonl)

## Convencoes

- **Linguagem:** specs em portugues, identificadores e schemas em ingles.
- **Datas relativas:** convertidas para absolutas.
- **IDs:** ULIDs para entidades de negocio; UUIDv4 onde precisao temporal nao importa.
- **Nomenclatura:** `snake_case` em DB e payloads JSON; `camelCase` em TypeScript;
  `PascalCase` em Pydantic models.
