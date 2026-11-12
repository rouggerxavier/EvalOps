# Classificação offline v1

A importação usa as mesmas rotas de datasets, snapshots, modelos, predições e avaliações da regressão. Nenhum código de modelo é carregado. Modelos clássicos e redes são produtores externos de predições.

Task schema: `{"task_type":"classification","label_set":["no","yes"],"positive_label":"yes","segments":["region"]}`. A ordem das classes é explícita e congelada no snapshot. Binário exige positive_label; multiclasse usa one-vs-rest para AUC. Limites: 100 classes, 10 mil amostras, 10 MiB, oito segmentos; produto classes × grupos (incluindo dataset) até 2 mil.

Referência: `{"label":"yes"}` ou null. Predição: `{"label":"yes","class_order":["no","yes"],"probabilities":[0.1,0.9]}`. Probabilidades são opcionais. Quando presentes, class_order deve ser idêntico ao label_set; valores finitos entre 0 e 1, soma 1 com tolerância absoluta 1e-9. Labels desconhecidos, IDs duplicados/desconhecidos e modelo/tarefa incompatíveis são recusados. A classe predita é declarada pelo produtor; a API não aplica argmax nem escolhe threshold silenciosamente.

Avalie com `{"prediction_set_id":"ID","evaluator":{"id":"classification.standard","version":"1","config":{}}}`. Config v1 é fixa: nenhum override de bins ou política de zero é aceito. SDK: `client.evaluate(project, predictions, evaluator="classification.standard", idempotency_key="OPERATION")`. CLI:

```bash
evalops evaluate --project PROJECT --prediction-set PREDICTIONS --evaluator classification.standard@1 --idempotency-key OPERATION --json
```

## Métricas e validade

Accuracy e matriz usam pares de labels válidos, com suporte por classe. Precision/recall/F1 usam contagens da matriz; micro agrega todas as classes, macro requer cada classe definida. Weighted usa suporte real e ignora somente classes de peso zero. Divisor zero retorna not_applicable, nunca zero. Uma classe com suporte zero continua visível na matriz. Referência rejeitada não entra no cálculo.

ROC-AUC agrupa empates de score. PR-AUC é average precision, sem interpolação trapezoidal. Binário usa a classe positiva explícita; multiclasse oferece métricas por classe e agregações ovr_macro/ovr_weighted. Ambas as classes são obrigatórias para cada AUC. Agregação com classe indefinida permanece not_applicable.

Brier, ECE e reliability v1 são binários: dez bins uniformes [0,1], último inclusivo. Reliability guarda probabilidade média, frequência positiva e contagem de cada bin; bin vazio é missing. ECE pondera diferença absoluta entre probabilidade média e frequência pelo tamanho do bin. Multiclasse retorna binary_only para essas três métricas.

Cada fato mantém sua população e cobertura. Accuracy usa labels; AUC/calibração usam referências com probabilidades, mesmo que o produtor não declare classe predita. Ausência de probabilidades deixa essas métricas not_applicable/missing_probabilities sem invalidar accuracy. As contagens podem, portanto, diferir entre métricas. Result.n_valid acompanha labels, não scores.

O avaliador persiste correctness por amostra; descoberta de erros e endpoint de amostras consultam esse resultado. Erro observado não é decisão de promoção. Sem política de classificação, decisão permanece inconclusive/no_quality_policy. Comparação pareada com política de tolerância continua exclusiva da regressão v1 e recusa snapshots de classificação.

## Evidência

Fixtures manuais cobrem matriz 2×2, accuracy .5, ROC-AUC .75, average precision 5/6, Brier .158125 e ECE .3375; empates completos dão ROC-AUC .5 e AP igual à prevalência. Classes ausentes, scores ausentes, grupos e entradas inválidas têm testes próprios. Fórmulas confrontadas com documentação primária de [métricas por classe](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.precision_recall_fscore_support.html), [ranking e average precision](https://github.com/scikit-learn/scikit-learn/blob/main/doc/modules/model_evaluation.rst) e [ROC-AUC](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.roc_auc_score.html). Não há dependência sklearn no runtime nem equivalência numérica verificada contra instalação local dessa biblioteca.

Interface: Avaliações por tarefa > Classificação offline. Importação por arquivo/editor com prévia, matriz de contagens, métricas por classe/segmento, erros por amostra e gráfico/tabela de calibração. Todos consultam fatos persistidos. E2E compara valores da web com API em 375/1280 px.
