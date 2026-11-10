# SPEC-005 — Runner e execução reproduzível

Status: **proposta, não implementada**. Data: 2026-11-09. Base: `545149b`.


## Problema, objetivo e escopo

Experimentos sintetizam textos e replay faz chamada LLM isolada. Avaliar aplicações reais exige executar código e dependências sob limites. Atender equipes que já possuem harness. Reusar fila arq, traces, reservas de custo e snapshots. Não substituir orquestrador de produção, assumir determinismo absoluto ou executar código enviado no processo API.

## Modos e contrato de execução

`mode=offline_predictions|local_model|application_adapter|llm_call_replay|agent_behavioral`. Offline só importa saída; local_model executa no ambiente cliente; application_adapter invoca harness versionado; llm_call_replay preserva replay atual; agent_behavioral recria sessão com ferramentas/estado sob fixtures. Uma comparação declara modo; nunca vende equivalência entre eles.

```json
{"schema_version":1,"mode":"application_adapter","environment":"dev","project_id":"p","snapshot_id":"s","candidate":{"application_ref":"support@abc","code_commit":"abc","code_dirty":false,"config_digest":"sha256:...","model_versions":["mv1"]},"adapter":{"id":"external-harness","version":"1","environment_digest":"sha256:..."},"evaluator_versions":["rubric:r@2"],"initial_state_digest":"sha256:...","fixture_digests":["sha256:..."],"seed":42,"repetitions":1,"limits":{"max_cost_usd":"1.00","wall_time_s":300,"max_tool_calls":20,"max_tokens":10000,"max_parallel":1},"effects_policy":"fixtures_only"}
```

Execução armazena manifest/hash, ExecutionAttempt, status, timestamps, exit_reason, producer/capture_status, budget_reserved/spent/unknown, prediction_set e trace/artifact refs. Repo/commit declarados não bastam: registrar dirty tree e hash de patch sem segredo, lockfile/deps, runtime, hardware e revisões de provider quando disponíveis. Seed é best effort; garantir repetibilidade do protocolo/evidência, não do texto.

## Interfaces e lifecycle

Owner registra runner via POST `/v1/projects/{p}/runners` com name, adapter_versions e ambientes permitidos; GET lista capabilities sem segredo; POST `/v1/runners/{id}/disable` impede novos leases. Credencial de runner possui escopo de lease/result próprio e nunca herda read geral. Execution.environment obrigatório é validado contra chave, runner e política.

POST `/v1/projects/{p}/executions` com plan_id pago e Idempotency-Key cria queued/202. MVP runner externo registrado pelo owner, associado ao projeto e capability; não endpoint arbitrário do cliente. Runner faz POST `/v1/runners/{id}/leases`, recebe execution_id/attempt_id/token limitado/manifest imutável/expiry. Heartbeat POST `/v1/executions/{id}/attempts/{a}/heartbeat`; upload de resultados sob IDs desse attempt; POST `/complete` sela hashes e resultado. Tokens nunca acessam outros projetos/runs. Lease, heartbeat e publicação revalidam origem/allowlist de todas as fontes e credencial original conforme SPEC-009; snapshot compartilhado não contorna ambiente. Lease TTL 60s renovado a cada 20s; expirado após início pago gera uncertain, não reexecução.

Transições: queued para running com lease único; running para succeeded/failed/timed_out/cancelled/uncertain. Cancelamento POST `/v1/executions/{id}/cancel` solicita interrupção; só marcar cancelled após ack ou isolamento encerrado. Lease cancelado não aceita publicação terminal tardia: registrar evidência tardia em tentativa sem sobrescrever estado; conciliação auditada. Retry cria attempt novo, com autorização e budget novo quando desfecho anterior incerto. At least once da fila não implica at least once de efeitos.

## Isolamento, custo e evidência

Runner externo precisa executar em container/processo dedicado do cliente, filesystem temporário, limite CPU/memória, sem montar credenciais de produção. Egress negado por padrão; allowlist apenas provider aprovado, fixtures para ferramentas. API não desreferencia URLs livres. A capacidade de conter código hostil no runner cliente deve ser declarada; não prometer sandbox gerenciado pelo EvalOps.

Classificar tools como read, simulated_write, external_write. Default fixtures_only impede external_write. Snapshot de catálogo/memória e estado inicial por caso; reset entre casos/conversas. Replay de conversa fixa sequência e política de branch, não só última mensagem. Logs/hashes de argumentos/retornos e versões entram como artefatos mascarados. Fixture ausente falha com categoria data, sem fallback para produção.

Reserva atômica de teto por organização/projeto antes de dispatch, Decimal, reusando padrões do replay e ledger novo da SPEC-009. Medição por chamada; verificação antes de próximo efeito. Limite não garante interromper requisição já aceita pelo provider; estimar margem e registrar overshoot. Unknown charge mantém reserva até reconciliação; nunca liberar e tentar novamente às cegas.

## Dependências e compatibilidade

SPEC-001/002/004/009 e comparação 007. Adicionar Execution/Attempt/Runner/Lease, sem reutilizar metadata de Trace como máquina de estados universal. Adaptar replay existente depois, com vínculo opcional e sem quebrar `/rerun`. SDK só envia/captura; core não importa Grankasa. Contrato do harness externo usa sample_id/conversation_id, output, spans e estado inicial.

## Testes e aceite

Harness local mínimo de dois turnos e ferramenta fake; mesmo fixture/manifest produz protocolo e evidência iguais, mesmo que outputs probabilísticos variem. Testar morte após gasto antes de complete, lease duplicado, cancelamento durante tool, timeout, retorno tardio, quota concorrente e tentativa de egress. Nenhum teste pode alterar produção. Validar Postgres/Redis reais em ambiente dedicado.

Grankasa piloto: fixtures de catálogo/sender, bateria selada e versões reais A/B, mesmo dataset e rubrica; relatório separa erro do juiz e do agente. Não aceitar comparador offline como prova de melhoria live.

## Plano incremental e riscos

1. Importação de resultados de harness externo, sem controlar processo.
2. Lease e runner local de modelo com reset/cancelamento.
3. Adaptador de aplicação; piloto de agente com tools fixture.
4. Hosting gerenciado só após experimento de isolamento/custo.

Riscos: efeitos externos, segredos em artefatos, versões não fixáveis e despesas incertas. Bloquear promoção quando captura/proveniência essenciais faltarem; reduzir escopo antes de introduzir infraestrutura nova.
