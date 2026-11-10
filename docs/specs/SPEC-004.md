# SPEC-004 — Integração AI-first

Status: **proposta, não implementada**. Data: 2026-11-09. Base: `545149b`.


## Problema e objetivo

Chaves já ingerem/leem e disparam batch de avaliação; datasets/experimentos/rerun ainda usam usuário pessoal em várias rotas. Agentes precisam operações completas e estado persistente, com o mesmo domínio da web. Atender Codex/Claude Code e automações sem JWT pessoal permanente. Excluir chat, agente autônomo embutido e regras duplicadas em adapters.

## Reuso, requisitos e arquitetura

Ampliar `ApiKey`, `actor_access`, `project_access`, ownership, rate limits e cliente httpx do SDK. API é autoridade. SDK chama HTTP; CLI usa SDK; MCP chama API. Não permitir DB direto. API keys antigas preservam scopes atuais. Principal de serviço identificado, revogável, com owner responsável; mapeamento em SPEC-009. SDK preserva tracer e feedback.

## Operações propostas

| Operação cliente | HTTP e resultado |
|---|---|
| discover_project | GET `/v1/projects/{p}/capabilities`: task_types, evaluator_versions, limits, permissions, links; não retorna segredos. Descoberta restrita ao projeto da chave. |
| find_failures | GET `/v1/projects/{p}/failures?kind=trace|sample&cursor=...`: evidência, validade e filtros aplicados; não classificar erro técnico como falha do modelo. |
| get_case | GET `/v1/datasets/{d}/items/{id}` mais estado de revisão/proveniência. |
| save_case | POST `/v1/datasets/{d}/cases`: input/expected_output?, source_refs, fixture_refs, reference_status=draft. Não alterar automaticamente caso já revisado. |
| run_evaluation | POST `/v1/projects/{p}/task-evaluations`; batch legado reutilizado para traces. |
| run_comparison | POST `/v1/experiments/{id}/comparisons`, SPEC-007. |
| get_experiment_result | GET `/v1/experiments/{id}/runs/{run_id}`; novos campos aditivos e kind. |
| get_evidence | GET `/v1/task-evaluations/{id}/samples` ou endpoint de trace existente, com links de artefatos autorizados. |

Listas/detalhes adicionais da SPEC-002 também são programáticos. Publicar OpenAPI e exemplos completos sem exigir que agente componha consultas SQL ou interprete HTML. IDs/referências resolvidos em API com autorização em toda relação.

## CLI/SDK/MCP e fluxos

SDK adiciona clientes de snapshots/predictions/task_evaluations/comparisons. CLI `evalops discover --project P --json`, `evalops evaluate --project P --prediction-set ID --evaluator regression.standard@1 --json` e `evalops result ID --json`. Token via env/config privado, nunca argumento ou log. Saída JSON íntegra stdout; progresso stderr. Exit 0 operação bem sucedida, 1 erro técnico, 2 contrato/uso; `--fail-on-decision` retorna 3 para fail, 4 review/inconclusive. Default não confunde qualidade com falha de transporte.

MVP: API+SDK+CLI; skill contém descoberta, limites, inspeção e links, sem regras de negócio. MCP local posterior com schemas estreitos e mesmos scopes; ferramentas readOnly/destructive anotadas como informação, autorização sempre no servidor. Remote MCP/OAuth só após revisar versão vigente do protocolo, resource audience e token forwarding; não inventar protocolo nesta fase.

Casos usam DatasetItem existente: GET de detalhe retorna revision e referência; PATCH `/v1/datasets/{d}/cases/{item}` exige If-Match, incrementa revision e preserva source_refs. Campos de revisão e proveniência ficam em metadata namespaced `evalops_case` com schema_version=1, validados no serviço. source refs fora do projeto são rejeitadas. Usuário member pode editar draft; reviewed exige ator humano autorizado e motivo, com auditoria. Agente só propõe draft.

## Idempotência e operações caras

Toda escrita nova exige `Idempotency-Key` até 128 caracteres. Unique(project_id,principal_id,method,path,key); hash do body canônico. Mesmo body retorna recurso anterior; body diferente 409. Gravar recibo e objeto na mesma transação; persistir pending antes do enqueue. Retenção mínima 7 dias; para operações pagas preservar recibo pelo prazo da execução e tombstone após expirar. Retry após prazo exige nova chave e intenção explícita.

Operação paga ou destrutiva requer plano prévio: POST `/v1/projects/{p}/operation-plans`, body operation/manifest_hash/max_cost/targets; devolve plan_id/expiry/estimate/required_permission. POST de execução carrega plan_id. Plano vinculado a ator/projeto/hash, expira em 15 minutos e é consumido atomicamente. Limites permanentes autorizados dispensam clique humano repetido quando operação dentro da política; fora disso exige aprovação owner registrada. UI e agentes seguem mesma regra. Offline bounded não exige plano pago. Replay legado mantém política atual até integração explícita.

## Retomada de investigação

Adicionar Investigation e InvestigationRevision: project_id, title, status, revision, hypotheses JSON, evidence_refs, run_ids, next_steps, decision?, author principal e timestamps; sem chain-of-thought privado. POST/GET `/v1/projects/{p}/investigations`; GET/PATCH `/v1/investigations/{id}` com If-Match/revision, 409 em edição concorrente. Histórico append-only, fontes tratadas como dados não confiáveis. Humano vê mesma investigação (SPEC-008). Subfase posterior ao MVP CLI, não requisito para cálculo inicial.

## Dependências, migração e riscos

SPEC-001/002/009, e 007 para comparação. Nova tabela de recibos/principal/investigação; adapters após serviços. Nenhum grant automático de execução às chaves read/ingest existentes. Riscos: resposta grande, ações repetidas, prompt injection em texto de traces e roubo de chave. Limitar paginação/tamanho e devolver resumo com links, sem remover evidência original autorizada.

## Testes, aceite e plano

Contrato API/SDK/CLI com mesma fixture e resultado; key read não executa, execute não administra membros, key projeto A não descobre B. Dois POST concorrentes com mesma chave criam um recurso; resposta perdida permite retomada sem nova cobrança. Testar revogação, cursor inválido, orçamento, plan replay e PATCH concorrente. Agente retoma investigação em sessão nova só pelo ID; humano abre mesmo histórico.

1. Principal/scopes e capabilities; 2. SDK/CLI offline e testes; 3. casos/comparação; 4. investigação web/API; 5. MCP local e, sob demanda, remote.
