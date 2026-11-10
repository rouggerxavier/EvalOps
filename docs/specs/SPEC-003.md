# SPEC-003 — Avaliação de Machine Learning tradicional

Status: **proposta, não implementada**. Data: 2026-11-09. Base: `545149b`.


## Problema, objetivo, reuso e limites

Sem avaliação numérica no produto atual. Primeiro atender regressão supervisionada offline: engenheiro importa predições de qualquer biblioteca, agente avalia o mesmo conjunto. Reusar snapshots/PredictionSet/TaskEvaluation da SPEC-002. Não executar modelo no servidor, treinar, carregar pickle, imputar labels, selecionar hiperparâmetros ou assumir vantagem sobre sklearn.

## Contrato do MVP de regressão

Task schema `{task_type:"regression",target:{name:"price",unit:"BRL"},segments:["region"]}`. SnapshotItem tem `expected_output:{value:10.0}`; Prediction tem `prediction:{value:12.0}`. Input é objeto tabular JSON; chave sample_id string estável, sem depender de ordem. Valores finitos obrigatórios; null/ausência de referência são missing, não zero. Prediction pode declarar erro de inferência; ausência de linha é contabilizada na cobertura. sample_id desconhecido/duplicado ou unidade conflitante rejeita importação.

MVP aceita apenas alvo escalar; sem pesos ou múltiplos targets. Fórmulas com resíduos `r=predicted-expected`: MAE=sum(abs(r))/n; MSE=sum(r²)/n; RMSE=sqrt(MSE); R²=1-SSE/SST. MAE/RMSE unidade do alvo, MSE unidade ao quadrado, R² adimensional e maximize. R² pode ser negativo; SST=0 ou n<2 retorna not_applicable com motivo, sem force_finite. n=0 deixa todas missing. Overflow retorna error, nunca Infinity.

Denominador de MAE/MSE/RMSE é n de pares válidos; R² explicita SST e n. Resíduos por amostra e agregados por segmento, com n_total/n_valid e cobertura. Segmento ausente usa grupo `__missing__`; não faz descarte silencioso. MVP sem ponderação; cada amostra pesa igualmente. Artefatos: série de resíduos vs predição, histograma com bordas fixadas na config e tabela de maiores erros. Histogramas comparados usam mesmas bordas.

## Extensões especializadas, fora da primeira vertical

| Tarefa | Contrato e condições de validade |
|---|---|
| Classificação | `label_set` ordenado, positivo explícito em binário, y_true/y_pred e probabilidades opcionais com ordem de classes. Accuracy e matriz sobre labels válidos; precision/recall/F1 por classe, macro/micro/weighted declarados. Divisor zero é not_applicable e não zero; reportar support. |
| ROC-AUC/PR-AUC | Exigem scores e ambas as classes; ROC via ranking com empate médio, PR definida como average precision na v1 (não interpolação trapezoidal). Multiclasse apenas one-vs-rest, agregação declarada. Missing probabilities não inviabiliza accuracy, mas impede AUC. |
| Calibração | Brier binário e reliability com 10 bins uniformes [0,1], último inclusivo; ECE=sum(n_bin/n)*abs(acc-confidence). Versionar bins; ausência de probabilidade é not_applicable. |
| Clustering | Silhouette só com features, distância declarada e 2<=k<n; não requer label verdadeiro. ruído e amostragem têm política explícita/seed; silhueta não prova utilidade de negócio. ARI só com referência externa. |
| Séries temporais | Split temporal, horizonte, frequência e timezone fixados; janelas sem leakage. Métricas por horizonte e comparação contra baseline ingênuo; não embaralhar amostras. Fase futura. |

Linear/logística, árvores, RF, boosting, XGBoost/LightGBM, SVM e KNN entram como produtores de predições com identidade; não precisam adapter por algoritmo para avaliação offline.

## Fluxos e interfaces

Web: Dataset tabular, snapshot, modelo/versão, upload/preview, avaliar, resíduos, casos. API/SDK usam rotas SPEC-002; `evaluator={id:"regression.standard",version:"1",config:{}}`. Mesmo response id/result usado por ambos. Comparação de versões em SPEC-007. Não recalcular fórmulas no browser.

## Não funcionais, dependências e compatibilidade

Depende SPEC-001/002/009 mínima; web e cliente SPEC-008/004 completam a vertical. Execução offline não usa provider nem reserva USD; custo não medido é null. Medir tempo do avaliador separado de latência de inferência importada. Preservar datasets textuais existentes; task_type novo não muda defaults legados. Novas tarefas só aparecem quando backend declarar suporte em capabilities.

## Testes, riscos e aceite

Fixture selada: y=[1,2,3], pred=[1,2,5] produz MAE=2/3, MSE=4/3, RMSE=sqrt(4/3), R²=-1; tolerância abs 1e-12. Alterar ordem das linhas não muda métricas/hash canônico. Null label reduz n_valid; label constante torna R² not_applicable. Testar overflow, segmentos vazios, ID duplicado e erro de inferência. Comparar fixtures com biblioteca de referência fixada em ambiente de testes, sem criar dependência runtime para quatro fórmulas.

Aceite vertical: usuário sem terminal importa fixture e obtém resultado; agente usa mesma entrada e obtém métricas iguais, denominadores iguais e link visível ao humano. Limite inicial 10 mil linhas/10 MiB com medição de memória/tempo publicada; orçamento alvo p95 <=5s em ambiente de teste identificado, sem claim de SLA produtivo. Se exceder, reduzir limite ou mover job para fila antes de liberar.

## Plano incremental

1. Parser/validação de contrato e métricas de regressão.
2. Métricas por amostra/grupo e visualizações.
3. Comparação limitada e piloto da vertical.
4. Classificação depois, com fixtures manuais de confusion/AUC/calibração; clustering e forecasting dependem de demanda.
