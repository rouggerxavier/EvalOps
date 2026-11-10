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
| MetricFact | id, task_evaluation_id, definition_id/version, scope `sample|group|dataset|model_version`, scope_key, value_type, value, unit, direction, state, reason?, n_total, n_valid, coverage, population_unit, aggregation, statistics, evidence_refs. Unique(run,definition/version,scope,scope_key). |
| Artifact | id, project_id, owner_type/id, sha256, media_type, bytes, storage_key interno, sensitivity, expires_at, status; nenhuma URL cliente para leitura automática. |

Chaves de projeto em pais e validação de todas as referências na mesma transação. Constraints compostas para relações novas quando suportadas; testes negativos obrigatórios em API e worker. `MetricFact` não vira EAV livre: catálogo de definições fixa tipos e schemas; IDs de avaliadores incluem implementação e versão.

Dataset recebe `task_type` e `task_schema` opcionais (default legado textual), validados pelo discriminante; snapshot congela ambos. Criar dataset novo aceita esses campos na rota existente, sem mudar shape de input dos itens antigos. Para task_type regression, expected_output.value e campos de segmentos são definidos pela SPEC-003. Fonte não revisada não vira referência humana.

PredictionSet, TaskEvaluation e Execution declaram `environment=dev|staging|prod`; avaliações herdam ambiente do PredictionSet, sem override. Comparação exige resultados do mesmo ambiente. Snapshots/modelos compartilham namespace de projeto, **não acesso irrestrito**. A política normativa e matriz de atores estão na [SPEC-009](SPEC-009.md#recursos-compartilhados-e-origem-dos-dados).

ModelVersion, Dataset/Item novos, DatasetSnapshot e Artifact recebem access label persistido `{origin_environments, allowed_environments, source_refs, label_schema_version:1, access_revision}`. Origens não podem ser apagadas por cópia; fontes referenciadas têm projeto e acesso conferidos. access_revision é inteiro monotônico para restrições, distinto de versão do schema. DatasetSnapshot materializa label junto ao conteúdo; segurança pode restringir acesso sem reescrever conteúdo/hash histórico. DatasetItem aplica label próprio e a restrição do dataset; snapshot usa interseção de todos os itens/fontes. Recursos legados sem origem verificável ficam indisponíveis para nova automação até classificação humana, sem mudar DTOs antigos; autorização das novas identidades também cobre rotas antigas conforme SPEC-009.

PredictionSet/TaskEvaluation/MetricFact/ExperimentRun, casos, investigações e todos os metadados, manifest, agregados, hashes, erros, contagens e artefatos derivados herdam interseção das permissões das fontes; resultado continua preso ao seu environment. Um artefato compartilhado não autoriza produzir resultado em ambiente fora de sua allowlist. Autorização é reavaliada em leitura, referência, cálculo, enqueue, início e publicação pelo worker; não confiar no acesso existente no momento do snapshot. Lista só pagina recursos acessíveis, sem revelar contagem/IDs/digest de recursos negados.

TaskEvaluation.decision é coluna nullable String(16) com CHECK da enum SPEC-001; terminal exige decision não nula e decision_reasons JSON. Não adicionar passed à tabela/DTO de tarefa. ExperimentRun usa migração/DTO específicos da SPEC-007; manter EvaluationRun/EvaluationScore intactos. TaskEvaluationDTO v1 inclui schema_version=1, kind=task_evaluation, id/project_id/environment, prediction_set_id/snapshot_id, status, decision/decision_reasons, n_total/n_valid/coverage, evaluator_manifest/config_hash, error, evidence_refs e timestamps; não possui passed. decision_reasons é lista de códigos, vazia se decisão não terminal null. task_evaluations sem política explícita retornam inconclusive/no_quality_policy conforme SPEC-001.

### Métodos adicionais para consumo completo

GET `/projects/{p}/model-versions` e `/model-versions/{id}`; GET `/projects/{p}/task-evaluations`; GET `/prediction-sets/{id}/rows`. Respeitar paginação SPEC-001 e filtros ambiente/status/model_version/snapshot. Resultados incluem kind, URLs web e links de evidência. A API calcula n_total/n_valid e coverage; nunca aceitar agregados calculados pelo browser como fatos locais verificados. Manifest importado identifica cálculo externo quando aplicável.

## Contratos de dados

### MetricFact v1: união tipada e população

Envelope de leitura completo: schema_version, id, task_evaluation_id, definition_id/version, scope/scope_key, value_type, value, unit, direction, state, reason, population_unit, n_total, n_valid, coverage, aggregation, statistics e evidence_refs. `direction=minimize|maximize|none`; definição versionada fixa tipo, unidade, população e fórmula. Unidade adimensional é `1`; unidades ao quadrado usam `BRL^2`. Catálogo é fechado por versão; campo desconhecido/versão incompatível é 422 na escrita, não coerção. Todos os números, inclusive statistics, normalization_count, cobertura, eixos e células/pontos, passam validação de finitude; campos inteiros rejeitam bool. R² measured/not_applicable com n_valid>0 exige sse/sst/target_mean; em missing/error sem estatísticas finitas disponíveis, statistics={} e reason obrigatório. SDK preserva JSON e UI renderiza o DTO recebido.

- `scalar`: value é número JSON finito, sem bool/string; `integer`: inteiro JSON não negativo nas definições de contagem, sem bool. Restrições adicionais vêm da definição (R² aceita negativo).
- `matrix`: value é `{row_axis:{name,labels},column_axis:{name,labels},cells}`. Labels são strings únicas não vazias e ordenadas; cells é retangular com dimensões exatas dos eixos. Cada célula é finita e não null; matriz de confusão exige inteiros >=0 e soma=n_valid. Eixo verdadeiro nas linhas e predito nas colunas; não transpor no SDK/web.
- `series`: value é `{x_axis:{name,unit},y_axis:{name,unit},points:[{key,x,y,state,reason}]}`. Key única; x finito; y finito quando measured, null com reason não vazio nos outros estados. Ordem explícita preservada, x duplicado só quando definição permitir (scatter de resíduos permite). Unit do envelope é unidade y; eixo x tem unidade própria. Nenhum NaN/Infinity aninhado.
- `state=measured` exige value válido e reason=null; `missing|not_applicable|error` exige value=null e reason código não vazio. Reason distingue ausência (`no_valid_pairs`), domínio (`constant_target`) e erro (`numeric_overflow`). Valores JSON ilegais são rejeitados antes de computar; overflow interno gera error sem Infinity serializado.
- `population_unit=sample|observation|point` é fixada pela definição, não pelo cliente. n_total inteiro >=0 conta unidades elegíveis do scope, n_valid conta as com insumos válidos usados; 0<=n_valid<=n_total. coverage=n_valid/n_total, ou null se n_total=0; não arredondar antes de comparar. Contagens continuam presentes em error/not_applicable para explicar insumos disponíveis. Métrica pode ser not_applicable com cobertura 1. TaskEvaluation.coverage usa pares predição/referência válidos / itens do snapshot, não a média das coberturas das métricas.
- `aggregation={method,normalization_count}`: method `mean|root_mean|r2|count|identity`; normalization_count é n_valid quando method=mean|root_mean e n_valid>0 (inclusive em erro interno); nos demais métodos é null. Em ausência de insumos, null. Não existe campo genérico denominator. R² usa `statistics={sse,sst,target_mean}` com quantidades `{value,unit}`, calculadas sobre os mesmos pares válidos; nunca armazenar SST como contagem. Outras definições usam statistics={} ou schema específico versionado.
- Séries de resíduos têm um ponto por sample e population_unit=sample. Em curva importada de treino, population_unit=point; pontos sem valor reduzem n_valid e aparecem como lacunas. Se ao menos um ponto for medido, série é measured; se nenhum, missing/value=null. Matriz sem população é missing/value=null, não matriz de zeros interpretada como medição.

Exemplos completos abaixo são fixtures documentais, não resultados de funcionalidades atuais. São exemplos de execuções distintas, identificadas por task_evaluation_id; não misturar métricas de tarefas diferentes no mesmo run. Valores da primeira fixture numérica constam na SPEC-003.

```json
[
  {"schema_version":1,"id":"mf_mae","task_evaluation_id":"te_fixture","definition_id":"regression.mae","definition_version":"1","scope":"dataset","scope_key":"all","value_type":"scalar","value":0.6666666666666666,"unit":"BRL","direction":"minimize","state":"measured","reason":null,"population_unit":"sample","n_total":3,"n_valid":3,"coverage":1.0,"aggregation":{"method":"mean","normalization_count":3},"statistics":{},"evidence_refs":[]},
  {"schema_version":1,"id":"mf_r2","task_evaluation_id":"te_fixture","definition_id":"regression.r2","definition_version":"1","scope":"dataset","scope_key":"all","value_type":"scalar","value":-1.0,"unit":"1","direction":"maximize","state":"measured","reason":null,"population_unit":"sample","n_total":3,"n_valid":3,"coverage":1.0,"aggregation":{"method":"r2","normalization_count":null},"statistics":{"sse":{"value":4.0,"unit":"BRL^2"},"sst":{"value":2.0,"unit":"BRL^2"},"target_mean":{"value":2.0,"unit":"BRL"}},"evidence_refs":[]},
  {"schema_version":1,"id":"mf_matrix","task_evaluation_id":"te_classification","definition_id":"classification.confusion","definition_version":"1","scope":"dataset","scope_key":"all","value_type":"matrix","value":{"row_axis":{"name":"actual","labels":["no","yes"]},"column_axis":{"name":"predicted","labels":["no","yes"]},"cells":[[1,1],[0,1]]},"unit":"count","direction":"none","state":"measured","reason":null,"population_unit":"sample","n_total":3,"n_valid":3,"coverage":1.0,"aggregation":{"method":"count","normalization_count":null},"statistics":{},"evidence_refs":[]},
  {"schema_version":1,"id":"mf_series","task_evaluation_id":"te_fixture","definition_id":"regression.residuals","definition_version":"1","scope":"dataset","scope_key":"all","value_type":"series","value":{"x_axis":{"name":"prediction","unit":"BRL"},"y_axis":{"name":"residual","unit":"BRL"},"points":[{"key":"s1","x":1.0,"y":0.0,"state":"measured","reason":null},{"key":"s2","x":2.0,"y":0.0,"state":"measured","reason":null},{"key":"s3","x":5.0,"y":2.0,"state":"measured","reason":null}]},"unit":"BRL","direction":"none","state":"measured","reason":null,"population_unit":"sample","n_total":3,"n_valid":3,"coverage":1.0,"aggregation":{"method":"identity","normalization_count":null},"statistics":{},"evidence_refs":[]},
  {"schema_version":1,"id":"mf_missing","task_evaluation_id":"te_no_pairs","definition_id":"regression.mae","definition_version":"1","scope":"dataset","scope_key":"all","value_type":"scalar","value":null,"unit":"BRL","direction":"minimize","state":"missing","reason":"no_valid_pairs","population_unit":"sample","n_total":3,"n_valid":0,"coverage":0.0,"aggregation":{"method":"mean","normalization_count":null},"statistics":{},"evidence_refs":[]},
  {"schema_version":1,"id":"mf_constant","task_evaluation_id":"te_constant","definition_id":"regression.r2","definition_version":"1","scope":"dataset","scope_key":"all","value_type":"scalar","value":null,"unit":"1","direction":"maximize","state":"not_applicable","reason":"constant_target","population_unit":"sample","n_total":3,"n_valid":3,"coverage":1.0,"aggregation":{"method":"r2","normalization_count":null},"statistics":{"sse":{"value":3.0,"unit":"BRL^2"},"sst":{"value":0.0,"unit":"BRL^2"},"target_mean":{"value":2.0,"unit":"BRL"}},"evidence_refs":[]},
  {"schema_version":1,"id":"mf_error","task_evaluation_id":"te_overflow","definition_id":"regression.mse","definition_version":"1","scope":"dataset","scope_key":"all","value_type":"scalar","value":null,"unit":"BRL^2","direction":"minimize","state":"error","reason":"numeric_overflow","population_unit":"sample","n_total":3,"n_valid":3,"coverage":1.0,"aggregation":{"method":"mean","normalization_count":3},"statistics":{},"evidence_refs":[]}
]
```

### Fixtures adversariais e aceite de serialização

Aplicar cada mutação ao envelope válido e esperar rejeição 422 sem gravar MetricFact: measured com value=null; scalar bool; matrix com célula `"NaN"`, row label duplicado, célula negativa ou dimensões divergentes; series com ponto measured/y=null, key repetida ou x=`1e309` (parser deve rejeitar resultado não finito); n_valid=4/n_total=3; coverage=0.5 quando 3/3; method=r2 com normalization_count=2; SST em unidade BRL em vez de BRL^2. JSON literal NaN/Infinity também é inválido. Corrupção no cálculo interno registra state=error, não resposta com número ilegal.

Aceite: os sete envelopes sobrevivem round-trip persistência/API/SDK/CLI sem perda de null, eixos, unidades, precisão ou motivo; UI distingue missing/error/not_applicable e zero medido, sem recalcular decisões. Testar série parcial com um ponto missing/y=null/reason=not_measured e coverage reduzida; recurso sem autorização não pode vazar por errors/evidence_refs. Os exemplos não são implementação de validador nem prova de runtime.

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
