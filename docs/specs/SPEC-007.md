# SPEC-007 — Experimentos, comparação e regressão

Status: **proposta, não implementada**. Data: 2026-11-09. Base: `545149b`.


## Problema, objetivo e reuso

Comparar médias sintéticas não mede versão real nem incerteza. Atender engenheiro, agente e responsável pela promoção. Reusar Experiment/ExperimentRun e datasets; novo tipo task_comparison liga variantes a TaskEvaluations. Excluir testes online A/B, deploy automático, causalidade e ranking universal entre tarefas.

## Modelo e contratos

Adicionar `Experiment.kind` default legacy_synthetic. Para task_comparison, `rubric_id` pode ser null; dataset_id continua obrigatório e snapshot_id fixa conteúdo. Check constraint exige rubrica no legado e snapshot no tipo novo. Variantes têm name único e model_version_id; ExperimentRun armazena run_metadata manifest/pairing_hash/policy_version. Associação ExperimentRunEvaluation(run_id,variant_name,task_evaluation_id) evita duplicar resultados. FK e serviço verificam mesmo projeto/snapshot. Não sobrescrever by_variant/comparisons históricos.

POST `/v1/projects/{p}/experiments` aceita novo discriminante apenas após serviço novo; serializer antigo preservado. POST `/v1/experiments/{id}/comparisons` com `{baseline_evaluation_id,candidate_evaluation_ids,policy}` e Idempotency-Key cria ExperimentRun, calcula e retorna 201 offline. GET existente com opt-in `view=task_v1` recupera DTO novo; default mantém contrato legado (abaixo). Para execução futura comparação só começa após candidatas terminais; falha de candidato deixa decisão inconclusive, nunca zero.

Policy v1: `{policy_version:"1",primary_metric:"regression.mae@1",max_degradation:0.0,min_pairs:30,required_coverage:1.0,critical_case_ids:[],critical_rules:[],confidence:null}`. direction vem da definição, não da conveniência do cliente. Delta bruto=candidate-baseline; degradation=delta para minimize, -delta para maximize; piora se degradation>max_degradation. Só comparar mesma versão de métrica/unidade, snapshot, conjunto de casos, config e protocolo. Modelo pode diferir; avaliador/fixtures não podem variar sem declarar comparação inválida. Captura parcial é explicitada.

## Incerteza e decisão

Offline MVP: diferença descritiva, sem afirmação de significância ou superioridade populacional. n_pairs conta IDs com insumos válidos nos dois lados para a métrica primária; n_total é total de itens do snapshot; pair_coverage=n_pairs/n_total (null se vazio). Recalcular agregados comparáveis sobre a mesma população pareada, sem misturar médias de subconjuntos diferentes; preservar métricas originais e reportar IDs excluídos a leitor autorizado. min_pairs inteiro >=1, default 30; required_coverage em [0,1], default 1.0. Snapshot vazio nunca passa. Override explícito de min_pairs/coverage integra nova policy selada e aparece no DTO/UI; não é evidência estatística.

Precedência determinística por candidato: (1) IDs inacessíveis são erro HTTP sem comparação; payload estrutural inválido é 422; (2) snapshot/config/métrica/unidade/ambiente/protocolo incompatíveis ou falta de métrica primária válida: inconclusive; (3) n_pairs<min_pairs ou cobertura insuficiente: inconclusive, mesmo com crítico reprovado (reportar bloqueio crítico separado); (4) com gates anteriores satisfeitos, qualquer crítico validamente fail ou degradation>max_degradation dá fail; (5) sem fail mas crítico missing/error/invalid reference dá inconclusive; (6) sem bloqueios e com críticos presentes, todos pass, exige revisão humana e decision=review; sem críticos e sem degradação, pass. Aprovação humana é registro separado e não muda decision=review. Motivos podem coexistir, mas não se perde a evidência de falha conhecida por causa de outro erro.

Ausência de predição é missing, não erro zero; teste abaixo do mínimo é inconclusive, não reprovação. Zero delta é empate descritivo. Ausência de significância ou intervalo cruzando limiar nunca prova equivalência. Em comparação com múltiplos candidatos persistir decisão/motivos por candidato; global é fail se algum fail, senão inconclusive se algum inconclusive, senão review se algum review, senão pass. Baseline não é candidato promovido.

Fase posterior: bootstrap pareado de diferenças por 2.000 reamostragens, seed fixo e IC percentil 95%, método/versionamento registrados. Para conversas, unidade de reamostragem é conversation_id; séries temporais exigem bloco temporal definido, sem bootstrap IID. Se intervalo cruza limiar de degradação, inconclusive para decisão estatística. Uma métrica primária predefinida; demais exploratórias sem alegação confirmatória/múltiplos testes.

Gate novo de tarefa usa política versionada vinculada ao ExperimentRun, sem alterar QualityGateConfig/serviço de produção. `decision` calcula qualidade; revisão humana é evento separado `{decision:approved|rejected|needs_changes,reason,evidence_refs,actor,created_at}` via POST `/v1/experiments/{id}/runs/{run}/reviews`. Sem alterar métricas ou implantar candidato. Aprovação exige permission admin e evidência suficiente; crítico pass por amostra leva a review agregado e exige revisão humana separada.

## Regra de casos críticos em regressão

critical_case_ids contém sample_ids do snapshot fixado (sem duplicatas); cada ID tem exatamente uma critical_rule e nenhum ID/rule extra. Falta, duplicação, regra sem limite, versão desconhecida, unidade diferente do target ou amostra inexistente: 422 antes da execução. Regra `regression.case_tolerance@1` mede absolute_error=abs(predicted-expected), unidade do alvo, minimize. Opcional relative_error=absolute_error/max(abs(expected),relative_epsilon), unidade `1`, minimize; relative_epsilon positivo e na unidade do alvo é obrigatório se houver max_relative_error. Ao menos um limite finito >=0; quando ambos, ambos devem passar (`<=`, sem arredondar). Não usar denominador relativo zero nem inferir epsilon.

Referência precisa ser finita, reference_status=reviewed e proveniência humana revisada no snapshot. Valor ausente, draft/rejected, referência não numérica ou só judge sem revisão: inconclusive/invalid_reference; não classificar candidato como errado. Predição ausente ou erro de inferência sem valor: inconclusive/missing_prediction; exceção/timeout/overflow no avaliador: inconclusive/evaluator_error, categoria evaluator. Medição válida que excede limite é fail, categoria model. Output por crítico: `{sample_id,rule_id,rule_version,config_hash,state,absolute_error,relative_error,decision,reason,reference_ref}`; valores não medidos null. `state` usa enum de métrica: measured nos erros numéricos válidos, missing em falta de predição/referência, not_applicable em referência draft/rejected e error em falha técnica. decision do crítico é pass/fail/inconclusive, não o agregado.

Exemplo completo de configuração selada antes de calcular comparação:

```json
{"policy_version":"1","primary_metric":"regression.mae@1","max_degradation":0.0,"min_pairs":30,"required_coverage":1.0,"critical_case_ids":["s01"],"critical_rules":[{"sample_id":"s01","evaluator_id":"regression.case_tolerance","evaluator_version":"1","config":{"unit":"BRL","max_absolute_error":2.0,"max_relative_error":0.02,"relative_epsilon":1.0}}],"confidence":null}
```

Fixture crítica independente dos valores de s01 da fixture de 30 pares: expected=100 BRL reviewed, predicted=101: absolute=1/relative=.01, case pass; predicted=103: absolute=3/relative=.03, case fail. Sem predição: missing, erros null, case inconclusive; expected=0/predicted=1 com epsilon=1 produz relative=1 (fail no limite .02). Exceção do avaliador produz error/inconclusive sem atribuir erro ao modelo. Para teste agregado usar snapshot de 30 casos cujo s01 tem expected=100, demais casos i=2..30 com predicted=expected; baseline no s01=102 (MAE=2/30). Candidato s01=101 passa métrica e crítico mas agregado review até revisão humana; s01=103 dá fail; sem predição s01 dá inconclusive por gates de pares/cobertura e crítico missing. Outro caso crítico draft com pares suficientes mantém inconclusive, sem silenciar fail já medido em crítico diferente.

policy_version/config/hash, referências e avaliador são fixados atomicamente **antes de ler/calcular outputs para decisão** e gravados no manifest do run. POST pode comparar resultados já existentes, mas policy não pode ser editada durante/depois desse run; policy escolhida após resultados conhecidos recebe `policy_timing=post_observation` e vale apenas como análise exploratória, sem promoção confirmatória. Regras predefinidas no plano antes de produzir candidatos recebem `predeclared`; origem/ator/timestamps auditados. Alterar tolerância exige nova versão, novo run e motivo visível; agentes não podem PATCH de critério no run existente (409), autoaprovar ou apagar resultado anterior. Gate crítico só autoriza promoção humana com policy predeclared e evidências suficientes; F1 é apenas comparação descritiva.

## Persistência, DTOs e rotas compatíveis

Reusar ExperimentRun com adição de `kind` (cópia imutável do Experiment.kind), coluna `decision` nullable String(16) com CHECK pass/review/fail/inconclusive e `decision_reasons` JSON. Não guardar enum apenas dentro de run_metadata nem recalcular ao ler. Backfill kind=legacy_synthetic e decision=null nas linhas existentes, mantendo passed/status/agregados byte-semanticamente iguais. Novo tipo usa passed=null **inclusive quando decision=fail**. CHECK: legacy_synthetic exige decision=null; task_comparison exige passed=null e, em status terminal, decision não null. Status do ExperimentRun continua running/completed/error para preservar storage atual: erro técnico terminal de comparação usa status=error, decision=inconclusive. TaskEvaluation mantém status SPEC-001; DTO não confunde os dois.

DTOs discriminados de leitura: `LegacyExperimentRunDTO` mantém ExperimentRunOut atual, com passed bool|null, sem campos novos no response default; discriminação é interna pelo kind persistido e pela view solicitada; `TaskComparisonRunDTO` tem schema_version=1, id/experiment_id/project_id/environment, kind=task_comparison, status, decision, decision_reasons, policy_version/policy_hash/policy_timing, snapshot_id, n_total/n_pairs/pair_coverage, resultados por candidato (evaluation_id,delta,degradation,decision,reasons,critical_results), manifest/evidence refs e timestamps. Não possui passed. SDK novo usa cliente legado para default e kind explícito para view=task_v1; UI lê decision, nunca faz truthiness. Revisão humana fica fora da enum de qualidade.

Compatibilidade HTTP: GET de lista/detalhe de experimentos e runs sem query preserva envelope/campos atuais e só mostra legacy_synthetic. ID task_comparison em GET default retorna 409 `task_view_required`, sem dados, após autorização. Opt-in `?view=task_v1` nas mesmas rotas lista/lê somente task_comparison e serializa DTO novo; envelopes de runs continuam `{data:[...]}` e `{run:...}`. `POST /experiments/{id}/run` continua só legado (task kind retorna 409 `comparison_endpoint_required`); POST /comparisons retorna `{run:TaskComparisonRunDTO}`/201 e exige kind novo. Listagem/get de Experiment com view=task_v1 usa schema_version/kind e rubric_id nullable; create sem kind segue schema legado obrigatório. Capabilities/SDK/web novos pedem view explícito. Não introduzir segunda tabela de comparações.

No DTO, n_total é tamanho do snapshot; n_pairs/pair_coverage no topo são o mínimo entre candidatos (null se nenhum; payload sem candidatos é 422); cada candidato inclui seus próprios n_total/n_pairs/pair_coverage, valores baseline/candidate/unit, delta e degradation, todos finitos ou null com reason. Decisão global usa precedência acima, não média de decisões. Sem política em TaskEvaluation, decision=inconclusive não impede comparar suas métricas válidas sob policy explícita; não promover essa decisão de entrada a pass por inferência.

Fixture de DTO para três pares, policy default e outputs iguais (modelos declarados distintos, mesmas predições):

```json
{"schema_version":1,"id":"exr_small","experiment_id":"exp_fixture","project_id":"p_fixture","environment":"dev","kind":"task_comparison","status":"completed","decision":"inconclusive","decision_reasons":["insufficient_pairs"],"policy_version":"1","policy_hash":"sha256:fixture-policy","policy_timing":"post_observation","snapshot_id":"snap_three","n_total":3,"n_pairs":3,"pair_coverage":1.0,"candidates":[{"evaluation_id":"te_candidate","n_total":3,"n_pairs":3,"pair_coverage":1.0,"baseline_value":0.6666666666666666,"candidate_value":0.6666666666666666,"unit":"BRL","delta":0.0,"degradation":0.0,"decision":"inconclusive","reasons":["insufficient_pairs"],"critical_results":[]}],"manifest":{"primary_metric":"regression.mae@1","baseline_evaluation_id":"te_baseline","min_pairs":30,"required_coverage":1.0,"max_degradation":0.0},"evidence_refs":[],"created_at":"2026-11-10T03:00:00Z","started_at":"2026-11-10T03:00:00Z","completed_at":"2026-11-10T03:00:01Z"}
```

IDs/digest acima são identificadores ilustrativos, não evidências existentes. Aceite de storage correspondente: passed SQL NULL, decision=inconclusive; serializer não acrescenta passed=false.

Histórico legado não recebe pass/fail por backfill: completed/false pode representar cálculo antigo insuficiente, e error/false é erro técnico. Leitor mostra “resultado legado”, passed original e limites, sem fingir protocolo novo. Comparação nova com resultado legado/sintético retorna 422 `incompatible_evaluation_kind`, não transforma false em falha de candidato real. Testes obrigatórios de leitura: manter JSON/semântica dos GETs legados; novo inconclusive tem decision explícita e nenhum passed no DTO; default não lista novo; view=task_v1 não lista legado; status=error/decision=inconclusive não aparece como modelo reprovado. Migração expand preserva linhas/IDs/nullable passed já existentes; sem downgrade destrutivo.

## Casos permanentes e fluxos

Salvar falha usa DatasetItem existente, source trace/sample refs, referência `draft|reviewed|rejected` e origem `observed|human|synthetic|judge`. Reference_status reviewed só via revisor humano autorizado, com motivo. Caso revisado usado em snapshot novo; nunca atualizar snapshot antigo. UX mostra comparação, drilldown pareado, casos persistentes e decisão. Agente tem mesmas operações, mas não pode se autoatribuir aprovação humana.

## Dependências e compatibilidade

SPEC-001/002/003/009; 004 para programático, 005 para candidato executado, 008 para UI. Migração expand para kind e associação; backfill legado explicitamente synthetic, sem chamar provider nem refazer resultados. Não reutilizar resultados sintéticos como baseline real. Índices de projeto/snapshot/status e plano de retenção dos artefatos.

## Riscos, testes e aceite

Riscos: cherry picking, leakage do holdout, juiz alterado depois de ver resultado e amostras dependentes. Preservar protocolo original e revisão; reavaliar ambos os lados sob novo avaliador, mantendo resultados antigos. Testar pairing com ordem distinta, sample faltante, label alterado, direção invertida, erro técnico e crítico. Resultado humano/API idêntico. A fixture de três amostras da SPEC-003 permanece inconclusive com default min_pairs=30, para empate ou piora. A fixture de 30 pares valida pass/fail descritivos, insuficiência e overrides explícitos. Testar crítico pass/fail/missing/error, policy alterada após observação e DTO inconclusive sem passed=false.

## Plano incremental

1. Associação e comparação offline descritiva.
2. Curadoria/revisão de casos e gate de tarefa.
3. Runner real com comparação pareada.
4. Estatística após piloto e validação de independência; sem promoção automática nesta SPEC.
