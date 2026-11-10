# SPEC-007 — Experimentos, comparação e regressão

Status: **proposta, não implementada**. Data: 2026-11-09. Base: `545149b`.


## Problema, objetivo e reuso

Comparar médias sintéticas não mede versão real nem incerteza. Atender engenheiro, agente e responsável pela promoção. Reusar Experiment/ExperimentRun e datasets; novo tipo task_comparison liga variantes a TaskEvaluations. Excluir testes online A/B, deploy automático, causalidade e ranking universal entre tarefas.

## Modelo e contratos

Adicionar `Experiment.kind` default legacy_synthetic. Para task_comparison, `rubric_id` pode ser null; dataset_id continua obrigatório e snapshot_id fixa conteúdo. Check constraint exige rubrica no legado e snapshot no tipo novo. Variantes têm name único e model_version_id; ExperimentRun armazena run_metadata manifest/pairing_hash/policy_version. Associação ExperimentRunEvaluation(run_id,variant_name,task_evaluation_id) evita duplicar resultados. FK e serviço verificam mesmo projeto/snapshot. Não sobrescrever by_variant/comparisons históricos.

POST `/v1/projects/{p}/experiments` aceita novo discriminante apenas após serviço novo; serializer antigo preservado. POST `/v1/experiments/{id}/comparisons` com `{baseline_evaluation_id,candidate_evaluation_ids,policy}` e Idempotency-Key cria ExperimentRun, calcula e retorna 201 offline. GET já existente recupera resultado com kind. Para execução futura comparação só começa após candidatas terminais; falha de candidato deixa decisão inconclusive, nunca zero.

Policy v1: `{primary_metric:"regression.mae@1",max_degradation:0.0,min_pairs:30,required_coverage:1.0,critical_case_ids:[],confidence:null}`. direction vem da definição, não da conveniência do cliente. Delta bruto=candidate-baseline; degradation=delta para minimize, -delta para maximize; piora se degradation>max_degradation. Só comparar mesma versão de métrica/unidade, snapshot, conjunto de casos, config e protocolo. Modelo pode diferir; avaliador/fixtures não podem variar sem declarar comparação inválida. Captura parcial é explicitada.

## Incerteza e decisão

Offline MVP: diferença descritiva, sem afirmação de significância ou superioridade populacional. Se n_pairs<min_pairs, coverage insuficiente, missing obrigatório ou config incompatível: inconclusive com motivos. Caso crítico validamente reprovado dá fail e pode bloquear independentemente da média; erro técnico nesse caso exige review/inconclusive, não falha do modelo. Zero diferença é empate descritivo, não melhoria.

Fase posterior: bootstrap pareado de diferenças por 2.000 reamostragens, seed fixo e IC percentil 95%, método/versionamento registrados. Para conversas, unidade de reamostragem é conversation_id; séries temporais exigem bloco temporal definido, sem bootstrap IID. Se intervalo cruza limiar de degradação, inconclusive para decisão estatística. Uma métrica primária predefinida; demais exploratórias sem alegação confirmatória/múltiplos testes.

Gate novo de tarefa usa política versionada vinculada ao ExperimentRun, sem alterar QualityGateConfig/serviço de produção. `decision` calcula qualidade; revisão humana é evento separado `{decision:approved|rejected|needs_changes,reason,evidence_refs,actor,created_at}` via POST `/v1/experiments/{id}/runs/{run}/reviews`. Sem alterar métricas ou implantar candidato. Aprovação exige permission admin e evidência suficiente; crítico requer revisão humana mesmo quando pass.

## Casos permanentes e fluxos

Salvar falha usa DatasetItem existente, source trace/sample refs, referência `draft|reviewed|rejected` e origem `observed|human|synthetic|judge`. Reference_status reviewed só via revisor humano autorizado, com motivo. Caso revisado usado em snapshot novo; nunca atualizar snapshot antigo. UX mostra comparação, drilldown pareado, casos persistentes e decisão. Agente tem mesmas operações, mas não pode se autoatribuir aprovação humana.

## Dependências e compatibilidade

SPEC-001/002/003/009; 004 para programático, 005 para candidato executado, 008 para UI. Migração expand para kind e associação; backfill legado explicitamente synthetic, sem chamar provider nem refazer resultados. Não reutilizar resultados sintéticos como baseline real. Índices de projeto/snapshot/status e plano de retenção dos artefatos.

## Riscos, testes e aceite

Riscos: cherry picking, leakage do holdout, juiz alterado depois de ver resultado e amostras dependentes. Preservar protocolo original e revisão; reavaliar ambos os lados sob novo avaliador, mantendo resultados antigos. Testar pairing com ordem distinta, sample faltante, label alterado, direção invertida, erro técnico e crítico. Resultado humano/API idêntico. Comparação da fixture com mesma saída tem delta zero; nova predição pior gera fail segundo policy sem confundir p-value.

## Plano incremental

1. Associação e comparação offline descritiva.
2. Curadoria/revisão de casos e gate de tarefa.
3. Runner real com comparação pareada.
4. Estatística após piloto e validação de independência; sem promoção automática nesta SPEC.
