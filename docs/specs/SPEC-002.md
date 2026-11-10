# SPEC-002 — Núcleo unificado de avaliação

Status: **proposta, não implementada**. Data: 2026-11-09. Base: `545149b`.


## Problema, objetivo e escopo

EvaluationRun e EvaluationScore servem rubricas por trace. DatasetItem é mutável. Criar avaliação de predições sem falsificar trace ou normalizar erro numérico. Usuários: engenheiro, revisor e clientes programáticos. Excluir treinamento, novo motor de tracing e reescrita do legado.

## Reuso e arquitetura

Reusar Project, Dataset/Item, Experiment/Run, AuditLog, ownership e limites de request. Adicionar entidades abaixo apenas para dados sem equivalente. Serviços transacionais compartilham autorização e stores, sem SQL em CLI/MCP.

| Entidade proposta | Campos mínimos e constraints |
|---|---|
| ModelVersion | id, project_id, name, version_ref, task_type, source_kind, external_ref?, artifact_digest?, provenance `verified|partial`, config JSON; unique(project_id,name,version_ref). Conteúdo imutável, conflito se mesma versão mudar. |
| DatasetSnapshot | id, project_id, dataset_id, schema_version, task_type, content_hash, item_count, task_schema, created_by/principal, created_at. Hash de conteúdo sem timestamps/IDs gerados. |
| SnapshotItem | snapshot_id, sample_id, source_item_id?, input, expected_output?, metadata, reference_status; PK(snapshot_id,sample_id). Cópia materializada independente do item vivo. |
| PredictionSet | id, project_id, snapshot_id, model_version_id, content_hash, producer_manifest, provenance; unique(project_id,snapshot_id,model_version_id,content_hash). |
| Prediction | set_id, sample_id, prediction, probability?, latency_ms?, error?, artifact_refs; PK(set_id,sample_id), FK ao item do mesmo snapshot. Não exigir trace. |
| TaskEvaluation | id, project_id, prediction_set_id, status, evaluator_manifest, config_hash, decision, coverage, error?, created_by/principal, timestamps. Resultados terminais imutáveis; reavaliação gera ID novo. |
| MetricFact | id, task_evaluation_id, definition_id/version, scope `sample|group|dataset|model_version`, scope_key, value_type, value, unit, direction, state, reason?, n_total, n_valid, denominator, evidence_refs. Unique(run,definition/version,scope,scope_key). |
| Artifact | id, project_id, owner_type/id, sha256, media_type, bytes, storage_key interno, sensitivity, expires_at, status; nenhuma URL cliente para leitura automática. |

Chaves de projeto em pais e validação de todas as referências na mesma transação. Constraints compostas para relações novas quando suportadas; testes negativos obrigatórios em API e worker. `MetricFact` não vira EAV livre: catálogo de definições fixa tipos e schemas; IDs de avaliadores incluem implementação e versão.

Dataset recebe `task_type` e `task_schema` opcionais (default legado textual), validados pelo discriminante; snapshot congela ambos. Criar dataset novo aceita esses campos na rota existente, sem mudar shape de input dos itens antigos. Para task_type regression, expected_output.value e campos de segmentos são definidos pela SPEC-003. Fonte não revisada não vira referência humana.

PredictionSet, TaskEvaluation e Execution declaram `environment=dev|staging|prod`; avaliações herdam ambiente do PredictionSet, sem override. Chave só escreve/executa/lê resultados novos do seu ambiente; humanos escolhem filtro explicitamente. Snapshots/modelos são recursos de projeto compartilhados entre ambientes, sem credenciais/estado produtivo embutidos. Enforcement novo não altera retroativamente permissões das rotas legadas sem teste e migração explícitos.

### Métodos adicionais para consumo completo

GET `/projects/{p}/model-versions` e `/model-versions/{id}`; GET `/projects/{p}/task-evaluations`; GET `/prediction-sets/{id}/rows`. Respeitar paginação SPEC-001 e filtros ambiente/status/model_version/snapshot. Resultados incluem kind, URLs web e links de evidência. A API calcula n_total/n_valid e coverage; nunca aceitar agregados calculados pelo browser como fatos locais verificados. Manifest importado identifica cálculo externo quando aplicável.

## Contratos de dados

```json
{"definition_id":"regression.rmse","definition_version":"1","scope":"dataset","scope_key":"all","value_type":"scalar","value":2.0,"unit":"BRL","direction":"minimize","state":"measured","reason":null,"n_total":3,"n_valid":3,"denominator":3,"evidence_refs":[]}
```

Tipos iniciais: scalar, integer, matrix, series; matrix tem eixos rotulados, series tem x/y e unidade. Missing/error/not_applicable exigem value null e reason; medido exige valor finito e n_valid coerente. `n_valid<=n_total`; denominador da métrica explícito, não necessariamente igual a n_valid (ex.: R² usa variância total). Nunca agregar médias sem pesos e populações. Scope model_version é limitado ao snapshot/run, não média global entre datasets.

Canonicalização: UTF-8 JSON com chaves ordenadas, separadores fixos, sem floats não finitos; ordenar amostras por sample_id; incluir task_schema, referências, estado de revisão, fixtures digests e metadados de segmentos. Snapshot criado em transação de leitura consistente; SHA-256 com versão do canonicalizador. Não deduplicar entre tenants. Alteração de rótulo gera novo snapshot.

## Interfaces propostas e fluxos

Prefixo `/v1`. POST `/projects/{p}/model-versions`; POST `/datasets/{d}/snapshots`; GET `/datasets/{d}/snapshots`; GET `/dataset-snapshots/{s}` e `/items`; POST `/projects/{p}/prediction-sets` recebe snapshot_id/model_version_id/manifest/rows; GET `/prediction-sets/{id}`; POST `/projects/{p}/task-evaluations` recebe prediction_set_id e evaluator `{id,version,config}`; GET `/task-evaluations/{id}`, `/metrics`, `/samples`; GET `/artifacts/{id}/download`. Escritas usam Idempotency-Key (SPEC-004).

MVP: até 10.000 linhas e 10 MiB por importação JSON; body limit efetivo deve admitir isso especificamente sem ampliar ingestão legado. Rejeitar arquivo inteiro em erro estrutural com no máximo 100 erros localizados; nenhuma gravação parcial. TaskEvaluation síncrona limitada retorna 201; execução futura retorna 202 com recurso consultável. Leitor GET sempre expõe status. Snapshot e PredictionSet criados retornam 201.

## Dependências e migrações

Depende SPEC-001 e subset de SPEC-009 (ownership, auditoria, limites). Expand adiciona tabelas sem alterar EvaluationRun/Score; datasets antigos continuam editáveis, snapshot criado sob demanda. HumanFeedback continua por trace; revisão de caso usa estado em DatasetItem.metadata validado e auditado até justificar entidade própria. Sem converter score antigo para MetricFact por inferência. Read model unificado opcional soma recursos com kind explícito, sem esconder validade legada.

## Riscos, testes e aceite

Risco de storage duplicado e referências apagadas: snapshots têm retenção própria, evidência expirada fica tombstone. Testar atomicidade, concorrência de snapshot com edição, FK cruzada, hash estável, duplicidade e erro de números. Editar DatasetItem depois de avaliar não muda resultado nem hash. Fixture RMSE maior que 1 persiste sem clipping. Snapshot sem referência humana não ganha status reviewed por importação.

## Plano incremental

1. Tabelas, DTOs, constraints e fixtures canônicas.
2. Snapshot e importação atômica com testes SQLite/PostgreSQL.
3. Serviço de métricas e GET de evidências.
4. Integrar clientes e benchmark limitado antes de aumentar volume.
