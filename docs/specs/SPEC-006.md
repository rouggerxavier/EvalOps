# SPEC-006 — Avaliação de Deep Learning

Status: **proposta, não implementada**. Data: 2026-11-09. Base: `545149b`.


## Problema, objetivo, reuso e escopo

Arquitetura neural não define a métrica: CNN de classificação e regressão linear podem compartilhar tarefa; modelos de detecção/áudio precisam contratos próprios. Atender engenheiros que já treinam em PyTorch/TensorFlow ou serviços externos. Reusar ModelVersion, snapshots, PredictionSet, MetricFact, Artifact e Execution. Não construir treino distribuído, tuner, scheduler GPU, framework de tensor ou model serving.

## Contratos especializados

ModelVersion declara `model_family=neural`, architecture opcional, external_ref e artifact digest; task_type determina schema. Não criar tabela CNN/Transformer nem exigir LLM messages. Pesos são referências/artefatos opacos, jamais deserializados pela API.

| Tarefa/dado | Contrato |
|---|---|
| Classificação/regressão neural | Mesmo contrato SPEC-003; métricas/segmentos idênticos para comparação com modelo clássico. |
| Detecção futura | Imagem com width/height/digest, boxes [x_min,y_min,x_max,y_max] em pixels, class_id, confidence; validação de bounds. mAP declara IoU thresholds, matching, classes ignoradas e versão. Sem config compatível retorna not_applicable. |
| Segmentação futura | Máscaras por artefato, dimensões/classes/ignore_index fixos; IoU e Dice por classe com política de classe ausente, support e macro explícitos. |
| ASR futuro | Referência/hipótese e idioma; WER=(S+D+I)/N com tokenizer/normalização versionados; N=0 not_applicable, WER pode exceder 1. CER separado. |
| Geração/multimodal | Rubrica/judge com evidência e referência humana quando disponível; sem forçar score a significar acurácia. |
| Treino importado | Artifact series `{name,split,step,epoch?,value,unit,recorded_at,source_ref}`; deduplicação por série/step/source, valores não finitos como error. Sem controlar loop de treino. |
| Recursos/inferência | hardware, accelerator, memory_peak_bytes, batch_size, precision, warmup_count, measured_count, duration_s e timing_method. Latência ms e throughput samples/s apenas se medidos; sem GPU inventada a partir do nome do modelo. |

## Arquitetura e interfaces

Primeira ampliação DL: importar resultados de classificação/regressão neural e curvas opcionais. POST `/v1/projects/{p}/artifact-imports` declara owner/hash/media_type/bytes, upload autenticado por ID alocado e finalize verificando hash/tamanho; limite inicial 10 MiB por artefato, MIME allowlist JSON/PNG sem HTML/SVG executável. POST `/v1/task-evaluations/{id}/evidence-links` pode anexar evidência externa sem alterar métrica selada; revisão registra evento e digest. Artefato não verificável tem provenance partial. Leitura usa download autorizado SPEC-002.

SPEC-008 renderiza curvas por split/step; dados faltantes viram lacunas. Comparar generalização exige splits e definições de loss equivalentes; loss de treino importada não prova qualidade em teste. Não misturar latência com warmup/hardware diferente. Métricas de recursos opcionais exibem not_measured; custo GPU depende de tarifa declarada/versionada e tempo, sem conversão implícita.

## Fluxos e não funcionais

Humano escolhe modelo neural, snapshot e predições; inspeciona mesmas métricas de tarefa. Agente importa mesmo manifest e abre resultados. Curvas podem vir de registry/experimento externo por referência; não executar notebooks no browser. Vídeo/áudio/imagem confidenciais usam política SPEC-009; evitar duplicar dataset bruto em cada run.

## Dependências e compatibilidade

SPEC-002/003 para primeira ampliação, 005 para execução controlada, 008/009 para artefatos/visualização. Extensões de schemas são discriminadas por task_type/schema_version; não transformar regression em DL-only. Nenhuma migração de traces. Tarefas futuras só são discoverable depois de avaliador/UI e fixtures implementados.

## Riscos, testes e aceite

Riscos de unidades, leakage e incompatibilidade de métricas externas. Testar curva com steps repetidos, split ausente, overflow, MIME disfarçado, hash incorreto e acesso cruzado. Dois produtores, clássico/neural, com predições iguais geram métricas iguais. Testes de detecção/ASR têm fixtures com matching/normalização calculados manualmente antes de liberar tarefa. Valores importados recebem origem e não substituem score calculado local sem concordância documentada.

## Plano incremental

1. Reusar regressão/classificação para redes, sem dependência de framework.
2. Importar curvas/recursos e visualizar proveniência.
3. Escolher uma tarefa visão ou áudio com usuário piloto e dataset autorizado.
4. Só depois ampliar detecção, segmentação e geração multimodal.
