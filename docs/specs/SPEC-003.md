# SPEC-003 — Avaliação de Machine Learning tradicional

Status: **proposta, não implementada**. Data: 2026-11-09. Base: `545149b`.


## Problema, objetivo, reuso e limites

Sem avaliação numérica no produto atual. Primeiro atender regressão supervisionada offline: engenheiro importa predições de qualquer biblioteca, agente avalia o mesmo conjunto. Reusar snapshots/PredictionSet/TaskEvaluation da SPEC-002. Não executar modelo no servidor, treinar, carregar pickle, imputar labels, selecionar hiperparâmetros ou assumir vantagem sobre sklearn.

## Contrato do MVP de regressão

Task schema `{task_type:"regression",target:{name:"price",unit:"BRL"},segments:["region"]}`. SnapshotItem tem `expected_output:{value:10.0}`; Prediction tem `prediction:{value:12.0}`. Input é objeto tabular JSON; chave sample_id string estável, sem depender de ordem. Valores finitos obrigatórios; null/ausência de referência são missing, não zero. Prediction pode declarar erro de inferência; ausência de linha é contabilizada na cobertura. sample_id desconhecido/duplicado ou unidade conflitante rejeita importação.

MVP aceita apenas alvo escalar; sem pesos ou múltiplos targets. Fórmulas com resíduos `r=predicted-expected`: MAE=sum(abs(r))/n; MSE=sum(r²)/n; RMSE=sqrt(MSE); R²=1-SSE/SST. MAE/RMSE unidade do alvo, MSE unidade ao quadrado, R² adimensional e maximize. R² pode ser negativo; SST=0 ou n<2 retorna not_applicable com motivo, sem force_finite. n=0 deixa todas missing. Overflow retorna error, nunca Infinity.

MAE/MSE/RMSE usam aggregation.normalization_count=n de pares válidos. R² usa aggregation.method=r2 e normalization_count=null, com statistics.sse/sst em unidade do alvo ao quadrado e statistics.target_mean na unidade do alvo (SPEC-002). n_total/n_valid/coverage são contagens/cobertura independentes do normalizador estatístico. Resíduos por amostra e agregados por segmento, com n_total/n_valid e cobertura. Segmento ausente usa grupo `__missing__`; não faz descarte silencioso. MVP sem ponderação; cada amostra pesa igualmente. Artefatos: série de resíduos vs predição, histograma com bordas fixadas na config e tabela de maiores erros. Histogramas comparados usam mesmas bordas.

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

### Fixtures de cálculo versus decisão

A fixture de três amostras acima testa somente cálculo. Com baseline idêntico e policy default min_pairs=30, comparação retorna inconclusive/insufficient_pairs, ainda que delta=0; com candidato pior também inconclusive. Override explícito min_pairs=3 é permitido somente em nova policy selada, identificada como ensaio pequeno; nunca alterar default silenciosamente. Não significância não demonstra equivalência.

Fixture de decisão `regression-comparison-30-v1`: sample_id=s01..s30; para inteiro i=1..30, referência y=i BRL, baseline=i+1, candidato A=i+0.5, candidato B=i+2. São **30 pares distintos**, não replicação da fixture pequena para fingir inferência estatística. Todos reference_status=reviewed, mesma origem sintética autorizada, mesmo snapshot/config/avaliador; coverage=1.0. JSON compacto de linhas completas `[sample_id,expected,baseline,candidate_a,candidate_b]`:

```json
[["s01",1,2,1.5,3],["s02",2,3,2.5,4],["s03",3,4,3.5,5],["s04",4,5,4.5,6],["s05",5,6,5.5,7],["s06",6,7,6.5,8],["s07",7,8,7.5,9],["s08",8,9,8.5,10],["s09",9,10,9.5,11],["s10",10,11,10.5,12],["s11",11,12,11.5,13],["s12",12,13,12.5,14],["s13",13,14,13.5,15],["s14",14,15,14.5,16],["s15",15,16,15.5,17],["s16",16,17,16.5,18],["s17",17,18,17.5,19],["s18",18,19,18.5,20],["s19",19,20,19.5,21],["s20",20,21,20.5,22],["s21",21,22,21.5,23],["s22",22,23,22.5,24],["s23",23,24,23.5,25],["s24",24,25,24.5,26],["s25",25,26,25.5,27],["s26",26,27,26.5,28],["s27",27,28,27.5,29],["s28",28,29,28.5,30],["s29",29,30,29.5,31],["s30",30,31,30.5,32]]
```

MAE baseline=1, A=0.5, B=2 BRL; MSE baseline=1, A=0.25, B=4 BRL^2; RMSE baseline=1, A=0.5, B=2 BRL. n_total=n_valid=n_pairs=30; SST=2247.5 BRL^2, SSE baseline=30/A=7.5/B=120 BRL^2. Policy default da SPEC-007, sem críticos: A tem delta=-0.5/degradation=-0.5 e pass; B tem delta=1/degradation=1 e fail. Resultado é conformidade descritiva com tolerância, sem conclusão estatística de superioridade/equivalência.

Remover uma predição: n_pairs=29 e coverage=29/30; inconclusive por insufficient_pairs e insufficient_coverage, mesmo que média restante seja melhor. Versão com referências constantes: MAE ainda medido; R² not_applicable/constant_target, statistics.sst.value=0. Confrontar estes resultados e os envelopes/erros da SPEC-002 na implementação, sem transformar checagem documental em teste de funcionalidade entregue.

## Plano incremental

1. Parser/validação de contrato e métricas de regressão.
2. Métricas por amostra/grupo e visualizações.
3. Comparação limitada e piloto da vertical.
4. Classificação depois, com fixtures manuais de confusion/AUC/calibração; clustering e forecasting dependem de demanda.
