# Referências oficiais e posicionamento — 2026-11-09

Pesquisa documental, sem benchmark, instalação ou validação comercial. Capacidades abaixo limitadas às páginas consultadas; preços, licenças, escalabilidade e equivalência de edições não foram comparados. URLs `latest` são móveis.

| Referência | Prática observada e fonte oficial | Implicação para EvalOps |
|---|---|---|
| MLflow | [Tracking](https://mlflow.org/docs/latest/ml/tracking) registra parâmetros, código, métricas e artefatos por run; [Registry](https://mlflow.org/docs/latest/ml/model-registry/) oferece versões e lineage. | Complementar com referências externas; não construir treinamento, serving ou registry completo. |
| W&B / Weave | [Avaliações](https://docs.coreweave.com/products/wandb/weave/guides/core-types/evaluations) organiza datasets, funções/modelos e scorers, com comparação e inspeção por exemplo. | Aprender separação entre execução e scoring; curvas como artefatos importados, sem gerenciar treino. A página de tracking redirecionou e não pôde ser lida; não fundamenta alegações aqui. |
| Evidently | [Monitoring](https://docs.evidentlyai.com/docs/platform/monitoring_overview) calcula reports em pipelines batch e persiste/visualiza; [métricas](https://evidentlyai.github.io/evidently/api-reference/main/evidently/metrics.html) incluem qualidade, performance e drift. | Drift é extensão futura, não inferir degradação sem labels. Considerar importador de reports após demanda. |
| Arize AX / Phoenix | [AX](https://arize.com/docs/ax) documenta observabilidade ML e agentes; [Phoenix](https://github.com/Arize-ai/phoenix) tem traces, datasets, experimentos e MCP; [runExperiment](https://arize-ai.github.io/phoenix/functions/_arizeai_phoenix-client.experiments_runExperiment.runExperiment.html) executa sobre exemplos e persiste resultados. | Reusar instrumentação via adaptadores quando demonstrar benefício; não criar outro padrão de tracing antes disso. |
| Langfuse | [Datasets](https://langfuse.com/docs/evaluation/experiments/datasets) compartilhados entre UI/SDK; [MCP](https://langfuse.com/docs/api-and-data-platform/features/mcp-server) autentica acesso a dados, distingue MCP documental e recomenda skill/CLI em ambientes shell. | AI-first já existe no mercado; priorizar API/SDK/CLI, MCP depois. |
| LangSmith | [Evaluation](https://docs.langchain.com/langsmith/evaluation) distingue offline/online e transforma trace em caso; [MCP](https://docs.langchain.com/langsmith/langsmith-mcp-server) documenta transição a remote MCP com OAuth. | Não atrelar adapter a framework; versões do protocolo e auth devem ser fixadas antes da fase MCP. |
| Braintrust | [Evaluate](https://docs.braintrust.dev/evaluate) articula datasets, scorers, experimentos e qualidade/regressão; há fluxos de anotação e online scoring documentados no índice. | Comparação e curadoria são consolidadas. Não alegar exclusividade para ciclo de falhas. Integração IDE específica não foi confirmada nesta pesquisa. |
| Promptfoo | [Configuração](https://www.promptfoo.dev/docs/configuration/guide/) combina prompts/providers/test cases/assertions; [assertions](https://www.promptfoo.dev/docs/configuration/expected-outputs/) aceita validação de saídas. | CLI reproduzível e matriz comparativa são referências; considerar intercâmbio de resultados, não copiar executor arbitrário para API. |

## Síntese separada por evidência

**Consolidado:** tracking de runs, datasets, avaliações, artefatos, comparação, observabilidade e interfaces SDK/API. MCP/skills aparecem em produtos existentes; não são diferencial por si.

**Já no EvalOps:** tracing, rubricas, feedback, gate, datasets mutáveis, comparação sintética e replay de chamada LLM. Ver [auditoria](../audits/estado-real-2026-11-09.md).

**Lacunas demonstradas no código:** snapshot imutável, métricas não normalizadas e seus denominadores, execução real de candidato, autorização programática completa e investigação persistente.

**Diferencial hipotético:** uma decisão de qualidade compreensível por humanos e agentes, apoiada na mesma evidência entre ML e sistemas agênticos. Validar com usuários e benchmark de tarefas; nenhuma superioridade comprovada.

## Comprar, integrar ou construir

Construir o núcleo mínimo de evidências, comparação e decisão com experiência humana existente. Aceitar `external_ref` de MLflow/W&B como identidade, sem dependência obrigatória ou sincronização bidirecional no MVP. Não implantar todos esses serviços. Importadores exigem demanda, contrato versionado e teste de equivalência de métricas. Scripts continuam alternativa legítima para tarefas locais pequenas; comparar esforço e erros, não apenas número de recursos.
