# SPEC-001 — Visão e contratos fundamentais

Status: **proposta, não implementada**. Data: 2026-11-09. Base: `545149b`.


## Problema, objetivo e usuários

O produto atual mede sistemas generativos, mas confunde potencialmente execução observada, replay e experimento sintético. Objetivo: avaliação e decisão compartilhadas por engenheiros, revisores e agentes de programação, abrangendo ML, DL e sistemas generativos. Não construir chatbot obrigatório, plataforma de treinamento, serving ou registry completo.

## Reuso e requisitos

Reusar organizações/projetos, web, API, SDK, traces, rubricas, feedback e gate. Requisito funcional: cada resultado oferece identidade, evidência, método e validade. Requisitos não funcionais: isolamento por projeto, compatibilidade aditiva e equivalência de resultados entre clientes. UX não exige terminal; agentes não exigem navegação visual.

## Vocabulário normativo

| Conceito | Contrato |
|---|---|
| Modelo | Artefato ou serviço que transforma input em output. Versão é identidade imutável ou referência declarada com proveniência parcial. |
| Aplicação de IA | Código/configuração que usa modelos e outros componentes para cumprir tarefa. |
| Agente | Aplicação que decide próximas ações, podendo usar ferramentas/memória. Não é sinônimo de chamada LLM. |
| Execução | Tentativa identificada de produzir predições/ações com manifest fixado. Pode falhar sem gerar trace completo. |
| Trace | Evidência observada com spans; pode representar parte de execução, sem capacidade de replay inerente. |
| Avaliação | Aplicação de método versionado a evidências; por trace no legado, por tarefa/dataset no novo núcleo. |
| Experimento | Plano de comparar variantes sob protocolo comum; ExperimentRun é uma realização desse plano. |
| Dataset | Coleção editável de casos; snapshot é versão materializada imutável. |
| Caso | Input, referência esperada opcional, contexto, fixtures e estado de revisão. Sample_id identifica caso dentro do snapshot. |
| Artefato | Objeto persistido com hash, tipo, tamanho, proprietário e política de acesso/retenção. |
| Métrica | Fato calculado com definição/versionamento, população, unidade, direção e estado de validade. |

## Contratos transversais e arquitetura

`schema_version=1` para novos envelopes. Identificadores opacos; nunca inferir tenant por slug ou campo do cliente. Timestamps UTC RFC3339. Decimais de USD como strings; métricas float finitas JSON, sem NaN/Infinity. Listas novas: `{data:[],next_cursor:null}`, limit default 50, máximo 200; cursor opaco ligado a projeto/filtro e ordenação estável `(created_at,id)`.

Eixos independentes: execution status `queued|running|succeeded|failed|cancelled|timed_out|uncertain`; metric state `measured|missing|not_applicable|error`; decisão `pass|review|fail|inconclusive`. Estado terminal não implica qualidade. Unknown outcome após chamada externa é `uncertain`, nunca retry automático pago.

Erro novo: `{error:{code,message,retryable,category,request_id,details}}`; categorias `data|model|evaluator|infrastructure|policy`. Códigos HTTP: 401 credencial, 403 escopo, 404 objeto invisível, 409 conflito/idempotência/estado, 413 limite, 422 contrato inválido, 429 cota, 503 infraestrutura indisponível. Não alterar envelope legado nesta entrega.

## Fluxos

Humano cria dataset, importa predições, solicita avaliação e abre evidência. Agente descobre capabilities, solicita mesma avaliação e entrega link ao mesmo resultado. Revisor registra decisão e motivo. Nenhum cliente recalcula métricas para produzir decisão autoritativa.

## Dependências, compatibilidade e migração

Sem dependência de outras SPECs; orienta todas. Não renomear entidades/rotas atuais. IDs de SPEC-001–009 estavam livres no inventário. Decisões arquiteturais detalhadas em [evolução](../architecture/evolucao.md).

## Riscos e aceite

Risco: abstração genérica apagar significado do trace. Aceite: schema de regressão não exige messages, tokens, rubric_id ou trace_id; schema legado continua exigindo seus campos. Teste de contrato distingue replay de chamada e execução de agente; exemplos de falha não viram score zero. Revisar linguagem da web sem redesenho.

## Plano incremental

1. Fixar OpenAPI e fixtures de envelopes antes de serviços.
2. Implementar SPEC-002/009 mínima; depois vertical SPEC-003/004/008.
3. Só ampliar tipos de tarefa após aceite da primeira vertical.
